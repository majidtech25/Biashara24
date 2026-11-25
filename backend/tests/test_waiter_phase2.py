"""Phase 2 contract, ownership, concurrency and printer delivery regression tests."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from unittest.mock import MagicMock
from decimal import Decimal
import pytest
from sqlalchemy import select, text, create_engine
from sqlalchemy.exc import IntegrityError
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Order, OrderItem, MenuItem, AuditLog
from app.models.waiter import TableReservation, OrderBatch
from app.migrations import upgrade
from test_integration import login, new_menu, new_table

@pytest.fixture
def workspace():
    with TestClient(app) as c:
        manager=login(c)
        waiter=login(c,"waiter@gmail.com","waiter123")
        username="second-"+uuid4().hex[:10]
        c.post("/api/admin/users",headers=manager,json={"username":username,"password":"Password123!","role":"waiter"})
        other=login(c,username,"Password123!")
        menu=new_menu(c,manager,10.15)
        table=new_table(c,manager)
        yield c,manager,waiter,other,menu,table

def create(w,quantity=3,table=None,key=None,owner=None):
    c,m,h,other,item,t=w
    return c.post("/api/orders",headers={**(owner or h),"Idempotency-Key":key or uuid4().hex},
                  json={"table_id":table or t,"items":[{"menu_item_id":item["id"],"quantity":quantity}]})

def add(w,o,quantity=1,key=None,version=None):
    c,m,h,other,item,t=w
    return c.post(f'/api/orders/{o["id"]}/items',headers={**h,"Idempotency-Key":key or uuid4().hex},
                  json={"expected_version":version or o["version"],"items":[{"menu_item_id":item["id"],"quantity":quantity}]})

def change(w,o,kind="remove",quantity=1):
    c,m,h,*_=w
    return c.post(f'/api/orders/{o["id"]}/change-requests',headers=h,json={
        "expected_version":o["version"],"kind":kind,"reason":"Customer changed their order",
        "items":[] if kind=="cancel" else [{"order_item_id":o["items"][0]["id"],"quantity":quantity}]})

def get(w,o):
    return w[0].get(f'/api/orders/{o["id"]}',headers=w[2]).json()

def pay(w,o,method="cash"):
    return w[0].post(f'/api/orders/{o["id"]}/clear',headers=w[1],json={
        "expected_version":o["version"],"amount":o["total"],"method":method,
        "reference":uuid4().hex if method=="m-pesa" else None})

def test_submission_price_snapshots_and_payment_lock(workspace):
    w=workspace;c,m,h,other,item,t=w
    r=create(w);assert r.status_code==201,r.text
    o=r.json();assert o["total"]==30.45 and o["version"]==1
    assert o["batches"][0]["deliveries"][0]["status"]=="not_configured"
    assert c.put(f'/api/admin/menu/{item["id"]}',headers=m,json={"price":12.25}).status_code==200
    r=add(w,o,2);assert r.status_code==201,r.text
    newer=r.json();assert newer["total"]==54.95 and newer["created_at"]==o["created_at"]
    assert newer["items"][0]["unit_price"]==10.15 and newer["items"][1]["unit_price"]==12.25
    assert newer["batches"][1]["kind"]=="addition" and len(newer["batches"][1]["items"])==1
    assert newer["batches"][1]["items"][0]["quantity"]==2
    assert pay(w,o).status_code==409
    assert pay(w,newer).status_code==201
    closed=get(w,o);assert closed["locked"]
    assert add(w,closed).status_code==409 and change(w,closed).status_code==409
    assert not next(x for x in c.get("/api/tables",headers=h).json() if x["id"]==t)["occupied"]
    with SessionLocal() as db:
        assert db.get(Order,o["id"]).total==Decimal("54.95")
        assert len(db.scalars(select(OrderBatch).where(OrderBatch.order_id==o["id"])).all())==2

def test_waiter_ownership_and_table_privacy(workspace):
    w=workspace;c,m,h,other,item,t=w;o=create(w).json()
    path=f'/api/orders/{o["id"]}'
    assert c.get(path,headers=other).status_code==404
    assert c.post(path+"/items",headers={**other,"Idempotency-Key":uuid4().hex},json={"expected_version":1,"items":[{"menu_item_id":item["id"],"quantity":1}]}).status_code==404
    assert c.post(path+"/change-requests",headers=other,json={"expected_version":1,"kind":"cancel","reason":"Please cancel"}).status_code==404
    assert o["id"] not in [x["id"] for x in c.get("/api/orders",headers=other).json()]
    table=next(x for x in c.get("/api/tables",headers=other).json() if x["id"]==t)
    assert table["occupied"] and table["owner"] and table["order_id"] is None
    assert "items" not in table and "total" not in table
    assert create(w,owner=other).status_code==409
    assert c.post("/api/tables",headers=h,json={"number":8111}).status_code==403
    assert c.get("/api/order-change-requests",headers=h).status_code==403

def test_table_validation_inactive_and_database_reservation(workspace):
    w=workspace;c,m,h,other,item,t=w
    assert c.post("/api/tables",headers=m,json={"number":0}).status_code==422
    table=next(x for x in c.get("/api/tables",headers=m).json() if x["id"]==t)
    assert c.post("/api/tables",headers=m,json={"number":table["number"]}).status_code==409
    assert c.put(f"/api/tables/{t}",headers=m,json={"is_active":False}).status_code==200
    assert create(w).status_code==400
    assert t not in [x["id"] for x in c.get("/api/tables",headers=h).json()]
    assert c.put(f"/api/tables/{t}",headers=m,json={"is_active":True}).status_code==200
    o=create(w).json()
    assert c.put(f"/api/tables/{t}",headers=m,json={"is_active":False}).status_code==409
    with SessionLocal() as db:
        db.add(TableReservation(table_id=t,order_id=o["id"]))
        with pytest.raises(IntegrityError):db.commit()
        db.rollback()
    assert c.put("/api/tables/999999",headers=m,json={"is_active":True}).status_code==404
    assert c.put(f'/api/admin/menu/{item["id"]}',headers=m,json={"active":False}).status_code==200
    assert add(w,o).status_code==400
    assert item["id"] not in [x["id"] for x in c.get("/api/menu",headers=h).json()]

def test_idempotency_and_uncertain_delivery_never_resends(workspace,monkeypatch):
    w=workspace;c,m,h,other,item,t=w
    assert c.post('/api/admin/printer-config',headers=m,json={"department_id":item["department_id"],"printer_ip":"192.168.1.44"}).status_code==200
    send=MagicMock(return_value={"status":"uncertain","error":"connection interrupted"})
    monkeypatch.setattr("app.services.printers_services.send_batch_ticket",send)
    key=uuid4().hex;o=create(w,key=key).json()
    assert o["batches"][0]["deliveries"][0]["status"]=="uncertain"
    replay=create(w,key=key);assert replay.status_code==201 and replay.json()["id"]==o["id"]
    assert send.call_count==1
    assert create(w,key=key,quantity=4).status_code==409
    key2=uuid4().hex
    a=add(w,o,key=key2);assert a.status_code==201,a.text
    assert add(w,o,key=key2).json()["total"]==40.60
    assert send.call_count==2
    entries=send.call_args.args[3]
    assert len(entries)==1 and entries[0]["quantity"]==1
    assert c.post("/api/orders",headers=h,json={"table_id":t,"items":[{"menu_item_id":item["id"],"quantity":1}]}).status_code==422

def test_removal_approval_retains_history_and_blocks_payment(workspace):
    w=workspace;c,m,h,other,item,t=w;o=create(w).json()
    req=change(w,o);assert req.status_code==201,req.text
    current=req.json()["order"];identity=req.json()["request_id"]
    assert current["total"]==o["total"] and current["payment_block_reason"]
    assert pay(w,current).status_code==409
    assert change(w,current).status_code==409
    added=add(w,current).json();assert added["total"]==40.60
    review=next(r for r in c.get("/api/order-change-requests",headers=m).json() if r["id"]==identity)
    assert review["resulting_total"]==30.45 and review["order"]["waiter"]
    decision=f"/api/order-change-requests/{identity}"
    assert c.put(decision,headers=m,json={"expected_version":current["version"],"decision":"approved"}).status_code==409
    approved=c.put(decision,headers=m,json={"expected_version":added["version"],"decision":"approved"})
    assert approved.status_code==200,approved.text
    result=approved.json();assert result["total"]==30.45 and not result["payment_block_reason"]
    assert result["items"][0]["quantity"]==2 and result["items"][0]["submitted_quantity"]==3 and result["items"][0]["voided_quantity"]==1
    assert result["batches"][-1]["kind"]=="correction" and result["batches"][-1]["items"][0]["quantity"]==-1
    assert c.put(decision,headers=m,json={"expected_version":result["version"],"decision":"approved"}).status_code==409
    assert pay(w,result).status_code==201
    with SessionLocal() as db:
        actions=set(db.scalars(select(AuditLog.action).where(AuditLog.entity_type=="orders",AuditLog.entity_id==o["id"])).all())
        assert {"create_bill","add_items","request_remove","approved_remove"}<=actions

def test_cancellation_rejection_and_approval_releases_table(workspace):
    w=workspace;c,m,h,other,item,t=w;o=create(w).json()
    req=change(w,o,"cancel").json();current=req["order"]
    assert add(w,current).status_code==409 and change(w,current,"cancel").status_code==409
    r=c.put(f'/api/order-change-requests/{req["request_id"]}',headers=m,json={"expected_version":current["version"],"decision":"rejected","reason":"Customer still wants the order"})
    assert r.status_code==200 and r.json()["total"]==o["total"] and len(r.json()["batches"])==1
    req=change(w,r.json(),"cancel").json()
    result=c.put(f'/api/order-change-requests/{req["request_id"]}',headers=m,json={"expected_version":req["order"]["version"],"decision":"approved"}).json()
    assert result["status"]=="cancelled" and result["total"]==0 and result["locked"]
    assert create(w).status_code==201

def test_request_validation_cashless_lock_and_release(workspace):
    w=workspace;c,m,h,other,item,t=w;o=create(w).json()
    assert change(w,o,quantity=4).status_code==400
    assert c.post(f'/api/orders/{o["id"]}/change-requests',headers=h,json={"expected_version":1,"kind":"remove","reason":"Need removal"}).status_code==400
    assert c.post(f'/api/orders/{o["id"]}/change-requests',headers=h,json={"expected_version":1,"kind":"cancel","reason":""}).status_code==422
    p=pay(w,o,"m-pesa");assert p.status_code==201,p.text
    pending=get(w,o);assert pending["locked"]
    assert add(w,pending).status_code==409 and change(w,pending).status_code==409
    assert create(w).status_code==409
    assert c.put(f'/api/payments/{p.json()["id"]}/verify',headers=m).status_code==200
    assert create(w).status_code==201

def test_fifo_sort_before_pagination_and_original_timestamp(workspace):
    w=workspace;c,m,h,other,item,t=w
    # A separate waiter avoids unrelated open bills from other tests.
    o1=create(w,owner=other).json();o2=create(w,table=new_table(c,m),owner=other).json()
    payload={"expected_version":o1["version"],"items":[{"menu_item_id":item["id"],"quantity":1}]}
    assert c.post(f'/api/orders/{o1["id"]}/items',headers={**other,"Idempotency-Key":uuid4().hex},json=payload).status_code==201
    path="/api/orders?active=true&sort=oldest&limit=1"
    assert c.get(path+"&offset=0",headers=other).json()[0]["id"]==o1["id"]
    assert c.get(path+"&offset=1",headers=other).json()[0]["id"]==o2["id"]
    assert c.get(f'/api/orders/{o1["id"]}',headers=other).json()["created_at"]==o1["created_at"]

def test_simultaneous_table_reservation(workspace):
    w=workspace
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda n:create(w,owner=w[2] if n==0 else w[3]).status_code,range(2)))
    assert sorted(results)==[201,409]

def test_concurrent_additions_and_duplicate_submissions(workspace):
    w=workspace;o=create(w).json()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:add(w,o).status_code,range(2)))
    assert sorted(results)==[201,409]
    current=get(w,o);assert current["total"]==40.60
    key=uuid4().hex
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:add(w,current,key=key).status_code,range(2)))
    assert results==[201,201] and get(w,o)["total"]==50.75

def test_payment_racing_addition_and_approval(workspace):
    w=workspace;c,m,h,*_=w;o=create(w).json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(add,w,o);p=pool.submit(pay,w,o);results=[a.result().status_code,p.result().status_code]
    assert sorted(results)==[201,409]
    o=create(w,table=new_table(c,m)).json();req=change(w,o).json();current=req["order"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(c.put,f'/api/order-change-requests/{req["request_id"]}',headers=m,json={"expected_version":current["version"],"decision":"approved"})
        p=pool.submit(pay,w,current)
        assert a.result().status_code==200 and p.result().status_code==409
    assert get(w,o)["total"]==20.30

def test_legacy_order_migration_preserves_prices_and_unassigned(tmp_path):
    target=tmp_path/"legacy.db";engine=create_engine("sqlite:///"+str(target))
    with engine.begin() as db:
        db.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY, order_number VARCHAR UNIQUE, waiter_id INTEGER, customer VARCHAR, notes TEXT, total FLOAT, status VARCHAR, created_at DATETIME, cleared_at DATETIME)"))
        db.execute(text("INSERT INTO orders VALUES (1,'OLD-1',1,'Table 27',NULL,21.37,'pending','2025-01-01',NULL)"))
        db.execute(text("CREATE TABLE order_items (id INTEGER PRIMARY KEY,order_id INTEGER,menu_item_id INTEGER,quantity INTEGER,price_at_time FLOAT,ready BOOLEAN)"))
        db.execute(text("INSERT INTO order_items VALUES (1,1,1,1,21.37,0)"))
    upgrade(engine);upgrade(engine)
    with engine.connect() as db:
        row=db.execute(text("SELECT total,table_id,version FROM orders WHERE id=1")).one()
        assert tuple(row)==(21.37,None,1)
        assert tuple(db.execute(text("SELECT price_at_time,voided_quantity FROM order_items")).one())==(21.37,0)
    assert len(list(tmp_path.glob("*.pre-v6-*.bak")))==1
    engine.dispose()

def test_batch_printer_payload_and_network_failures(workspace,monkeypatch):
    from app.models import Department
    from app.services.printers_services import send_batch_ticket
    w=workspace;o=create(w).json();addition=add(w,o).json()
    connection=MagicMock()
    socket=MagicMock();socket.__enter__.return_value=connection
    connect=MagicMock(return_value=socket)
    monkeypatch.setattr("app.services.printers_services.socket.create_connection",connect)
    with SessionLocal() as db:
        order=db.get(Order,o["id"])
        submission=db.get(OrderBatch,addition["batches"][-1]["id"])
        department=db.get(Department,w[4]["department_id"])
        assert send_batch_ticket(department,order,submission,submission.items,1)["status"]=="not_configured"
        department.printer_ip="192.168.1.22"
        assert send_batch_ticket(department,order,submission,submission.items,1)["status"]=="sent"
        ticket=connection.sendall.call_args.args[0].decode("cp437")
        assert "ADDITIONAL ITEMS" in ticket and "Table: 1" in ticket and "Waiter:" in ticket
        assert "1 x " in ticket and "3 x " not in ticket and submission.created_at.isoformat() in ticket
        # Sending failed after the connection opened: part of the ticket may have printed.
        connection.sendall.side_effect=OSError("Partial delivery")
        assert send_batch_ticket(department,order,submission,submission.items,1)["status"]=="uncertain"
        # The printer could not be reached: nothing printed, so it is safe to try again.
        connect.side_effect=OSError("No route to host")
        assert send_batch_ticket(department,order,submission,submission.items,1)["status"]=="not_sent"
        department.printer_ip="127.0.0.1"
        assert send_batch_ticket(department,order,submission,submission.items,1)["status"]=="failed"

def test_legacy_original_stays_visible_after_addition(workspace):
    w=workspace;c,m,h,other,item,t=w
    waiter_id=c.get('/auth/me',headers=h).json()['id']
    with SessionLocal() as db:
        legacy=Order(order_number='LEGACY-'+uuid4().hex[:12],waiter_id=waiter_id,customer='Table 47',total=10.5,status='pending',version=1)
        legacy.items.append(OrderItem(menu_item_id=item['id'],quantity=2,voided_quantity=0,price_at_time=5.25))
        db.add(legacy);db.commit();identity=legacy.id
    before=c.get(f'/api/orders/{identity}',headers=h).json()
    assert before['table_number'] is None and before['batches'][0]['kind']=='original (legacy)'
    after=add(w,before).json()
    assert after['total']==20.65
    assert len(after['batches'])==2
    assert after['batches'][0]['items'][0]['unit_price']==5.25
    assert after['batches'][0]['items'][0]['quantity']==2
    assert after['batches'][1]['kind']=='addition'


def test_only_waiters_send_orders_to_the_kitchen():
    """Majid, 2026-11-25: the kitchen receives only orders that waiters post."""
    with TestClient(app) as c:
        for email, password in (("manager@gmail.com", "manager123"), ("director@gmail.com", "director123"), ("cashier@gmail.com", "cashier123")):
            token = c.post("/auth/login", json={"username": email, "password": password}).json()["access_token"]
            h = {"Authorization": "Bearer " + token, "Idempotency-Key": uuid4().hex}
            assert c.post("/api/orders", headers=h, json={"items": [{"menu_item_id": 1, "quantity": 1}]}).status_code == 403
            assert c.post("/api/orders/1/items", headers=h, json={"expected_version": 1, "items": [{"menu_item_id": 1, "quantity": 1}]}).status_code == 403
