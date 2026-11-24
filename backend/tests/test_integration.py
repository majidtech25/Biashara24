from concurrent.futures import ThreadPoolExecutor
from datetime import date
from uuid import uuid4
from unittest.mock import MagicMock
import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text, select
from app.main import app
from app.database import SessionLocal
from app.models import Order, Ingredient, AuditLog
from app.migrations import upgrade

def login(c, email="director@gmail.com", password="director123"):
    response=c.post("/auth/login",json={"username":email,"password":password})
    assert response.status_code==200,response.text
    return {"Authorization":"Bearer "+response.json()["access_token"]}

@pytest.fixture
def client():
    with TestClient(app) as c: yield c

def new_menu(c,h,price=120):
    suffix=uuid4().hex[:8]
    category=c.post("/api/admin/categories",headers=h,json={"name":"Food "+suffix}).json()
    department=c.post("/api/admin/departments",headers=h,json={"name":"Kitchen "+suffix}).json()
    r=c.post("/api/admin/menu",headers=h,json={"name":"Meal "+suffix,"price":price,"category_id":category["id"],"department_id":department["id"]})
    assert r.status_code==201,r.text
    return r.json()

def new_table(c,h):
    used={t["number"] for t in c.get("/api/tables",headers=h).json()}
    number=next(n for n in range(1,10000) if n not in used)
    result=c.post("/api/tables",headers=h,json={"number":number})
    assert result.status_code==201,result.text
    return result.json()["id"]

def new_order(c,h):
    a,b=new_menu(c,h,120),new_menu(c,h,80)
    r=c.post("/api/orders",headers={**h,"Idempotency-Key":uuid4().hex},json={"table_id":new_table(c,h),"items":[{"menu_item_id":a["id"],"quantity":2},{"menu_item_id":b["id"],"quantity":1}]})
    assert r.status_code==201,r.text
    assert r.json()["total"]==320
    return r.json()

def test_waiter_cashier_director_persistence(client):
    c=client;director=login(c)
    email="waiter-"+uuid4().hex[:8]+"@example.com"
    assert c.post("/api/admin/users",headers=director,json={"username":email,"password":"Password123!","role":"waiter"}).status_code==201
    waiter=login(c,email,"Password123!")
    a,b=new_menu(c,director),new_menu(c,director,80)
    r=c.post("/api/orders",headers={**waiter,"Idempotency-Key":uuid4().hex},json={"table_id":new_table(c,director),"items":[{"menu_item_id":a["id"],"quantity":2},{"menu_item_id":b["id"],"quantity":1}]})
    assert r.status_code==201
    order=r.json()
    assert order["order_number"] and len(order["items"])==2
    assert order["id"] in [o["id"] for o in c.get("/api/orders/waiter/pending-bills",headers=waiter).json()]
    cashier=login(c,"cashier@gmail.com","cashier123")
    before=c.get("/api/dashboard",headers=director).json()["revenue"]["restaurant"]["total"]
    assert c.get("/api/orders/"+str(order["id"]),headers=cashier).status_code==200
    r=c.post(f'/api/orders/{order["id"]}/clear',headers=cashier,json={"expected_version":order["version"],"amount":320,"method":"cash"})
    assert r.status_code==201 and r.json()["status"]=="completed"
    assert c.get(f'/api/orders/{order["id"]}',headers=cashier).json()["status"]=="cleared"
    assert c.get("/api/dashboard",headers=director).json()["revenue"]["restaurant"]["total"]==before+320
    assert c.get("/api/reports/daily",headers=director).json()["restaurant"]["revenue"]==before+320
    # New database session and new authenticated client, equivalent to a browser reload.
    with SessionLocal() as db: assert db.get(Order,order["id"]).total==320
    with TestClient(app) as fresh:
        assert fresh.get("/api/dashboard",headers=login(fresh)).json()["revenue"]["restaurant"]["total"]==before+320

def test_manual_cashless_confirmation_and_totals(client):
    c=client;h=login(c);o=new_order(c,h)
    before=c.get("/api/payments/daily-summary",headers=h).json()
    r=c.post(f'/api/orders/{o["id"]}/clear',headers=h,json={"expected_version":o["version"],"amount":320,"method":"m-pesa","reference_number":"REF"+uuid4().hex[:10]})
    assert r.status_code==201 and r.json()["status"]=="pending"
    payment=r.json()
    assert c.get("/api/payments/daily-summary",headers=h).json()["total_revenue"]==before["total_revenue"]
    assert c.put(f'/api/payments/{payment["id"]}/verify',headers=h).json()["status"]=="completed"
    assert c.put(f'/api/payments/{payment["id"]}/verify',headers=h).status_code==200
    after=c.get("/api/payments/daily-summary",headers=h).json()
    assert after["mpesa_count"]==before["mpesa_count"]+1
    assert after["mpesa_total"]==before["mpesa_total"]+320
    assert after["total_revenue"]==round(after["cash_total"]+after["mpesa_total"],2)
    assert c.post(f'/api/orders/{o["id"]}/clear',headers=h,json={"expected_version":o["version"],"amount":320,"method":"cash"}).status_code==409
    assert c.delete(f'/api/orders/{o["id"]}',headers=h).status_code==409
    with SessionLocal() as db:
        assert db.scalar(select(AuditLog).where(AuditLog.entity_id==payment["id"],AuditLog.action=="manual_receipt_confirmation"))

def test_payment_validation_cancel_and_concurrency(client):
    c=client;h=login(c);o=new_order(c,h);path=f'/api/orders/{o["id"]}/clear'
    assert c.post(path,headers=h,json={"expected_version":o["version"],"amount":1,"method":"cash"}).status_code==400
    assert c.post(path,headers=h,json={"expected_version":o["version"],"amount":320,"method":"m-pesa"}).status_code==400
    assert c.put(f'/api/orders/{o["id"]}',headers=h,json={"new_status":"cleared"}).status_code==409
    def pay(_): return c.post(path,headers=h,json={"expected_version":o["version"],"amount":320,"method":"cash"}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool: outcomes=list(pool.map(pay,range(2)))
    assert sorted(outcomes)==[201,409]
    o=new_order(c,h)
    assert c.delete(f'/api/orders/{o["id"]}',headers=h).status_code==204
    assert c.post(f'/api/orders/{o["id"]}/clear',headers=h,json={"expected_version":o["version"],"amount":320,"method":"cash"}).status_code==409

def test_stock_persistence_history_and_low_alerts(client):
    c=client;h=login(c,"manager@gmail.com","manager123")
    r=c.post("/api/stock/ingredients",headers=h,json={"name":"Rice "+uuid4().hex[:8],"unit":"kg","min_level":5})
    assert r.status_code==201
    identity=r.json()["id"]
    r=c.post("/api/stock/add",headers=h,json={"ingredient_id":identity,"quantity":3,"reason":"Delivery"})
    assert r.status_code==201 and r.json()["new_stock_level"]==3
    assert identity in [i["id"] for i in c.get("/api/stock/low-items",headers=h).json()["items"]]
    c.post("/api/stock/add",headers=h,json={"ingredient_id":identity,"quantity":4,"reason":"Delivery"})
    assert identity not in [i["id"] for i in c.get("/api/stock/low-items",headers=h).json()["items"]]
    r=c.post("/api/stock/adjust",headers=h,json={"ingredient_id":identity,"quantity":5,"reason":"Count"})
    assert r.json()["old_quantity"]==7 and r.json()["new_quantity"]==5
    assert c.get(f"/api/stock/ingredients/{identity}",headers=h).json()["current_stock"]==5
    assert c.post("/api/stock/deduct",headers=h,json={"ingredient_id":identity,"quantity":6}).status_code==409
    tx=c.get(f"/api/stock/history?ingredient_id={identity}&transaction_type=adjust",headers=h).json()
    assert len(tx)==1 and tx[0]["quantity_before"]==7 and tx[0]["quantity_after"]==5
    with SessionLocal() as db: assert db.get(Ingredient,identity).current_stock==5
    with TestClient(app) as fresh: assert fresh.get(f"/api/stock/ingredients/{identity}",headers=login(fresh)).json()["current_stock"]==5

def test_carwash_persistence_confirmation_and_history(client):
    c=client;h=login(c)
    bay=c.post("/api/carwash/bays",headers=h,json={"bay_number":int(uuid4().hex[:6],16),"name":"Test bay"}).json()
    service=c.post("/api/carwash/services",headers=h,json={"name":"Wash "+uuid4().hex[:8],"price":500}).json()
    cashier=login(c,"cashier@gmail.com","cashier123")
    before=c.get("/api/carwash/today",headers=cashier).json()["summary"]
    payload={"bay_id":bay["id"],"service_id":service["id"],"vehicle_plate":"kda 482m","vehicle_type":"saloon","amount":500,"payment_method":"cash"}
    r=c.post("/api/carwash/transaction",headers=cashier,json=payload)
    assert r.status_code==201,r.text
    wash=r.json();assert wash["transaction_number"] and wash["vehicle_plate"]=="KDA 482M"
    assert c.get("/api/carwash/today",headers=cashier).json()["summary"]["cash_total"]==before["cash_total"]+500
    # The bay is busy until this car is washed; a second car must wait.
    assert c.post("/api/carwash/transaction",headers=cashier,json=payload).status_code==409
    attendant=c.post("/api/carwash/attendants",headers=h,json={"name":"Otieno"}).json()
    assert c.put(f'/api/carwash/{wash["id"]}/wash',headers=cashier,json={"status":"washing","attendant_id":attendant["id"]}).status_code==200
    assert c.put(f'/api/carwash/{wash["id"]}/wash',headers=cashier,json={"status":"done"}).json()["wash_status"]=="done"
    payload.update(payment_method="m-pesa",mpesa_reference="WASH"+uuid4().hex[:8])
    r=c.post("/api/carwash/transaction",headers=cashier,json=payload);assert r.json()["payment_status"]=="pending"
    assert c.post(f'/api/carwash/{r.json()["id"]}/complete',headers=cashier).json()["payment_status"]=="completed"
    with TestClient(app) as fresh:
        data=fresh.get("/api/carwash/history?payment_method=cash&from_date="+str(date.today()),headers=login(fresh)).json()
        assert wash["id"] in [x["id"] for x in data["transactions"]]
        assert data["summary"]["cash_total"]>=500

def test_reports_exports_and_dashboard(client):
    c=client;h=login(c)
    dashboard=c.get("/api/dashboard",headers=h).json()
    today=dashboard["date"]
    r=dashboard["revenue"];assert r["combined"]==r["restaurant"]["total"]+r["carwash"]["total"]
    items=c.get("/api/dashboard/top-items",headers=h).json()["items"]
    assert [i["quantity"] for i in items]==sorted([i["quantity"] for i in items],reverse=True)
    assert dashboard["stock_alerts"]["count"]==c.get("/api/stock/low-items",headers=h).json()["count"]
    revenue=c.get(f"/api/dashboard/revenue?from_date={today}&to_date={today}",headers=h).json()
    assert revenue["days"][0]["total"]==r["combined"]
    assert len(c.get("/api/dashboard/trends?period=weekly",headers=h).json()["points"])==7
    assert len(c.get("/api/reports/weekly?week_start="+today,headers=h).json()["days"])==7
    assert c.get("/api/reports/monthly?month=13",headers=h).status_code==422
    assert c.get("/api/reports/export?from_date=2020-01-01&to_date="+today,headers=h).status_code==400
    csv=c.get("/api/reports/export?format=csv",headers=h)
    assert csv.status_code==200 and "Restaurant M-Pesa" in csv.text and "Current low stock" in csv.text
    pdf=c.get("/api/reports/export?format=pdf",headers=h)
    assert pdf.status_code==200 and pdf.content.startswith(b"%PDF-")
    from pypdf import PdfReader
    assert "Biashara360" in PdfReader(io.BytesIO(pdf.content)).pages[0].extract_text()

@pytest.mark.parametrize("path",["/api/orders","/api/payments","/api/payments/daily-summary","/api/stock/ingredients","/api/stock/low-items","/api/carwash/today","/api/dashboard","/api/dashboard/revenue","/api/dashboard/top-items","/api/reports/daily","/api/reports/export","/api/admin/audit-logs"])
def test_protected_routes(client,path):
    assert client.get(path).status_code==401
    assert client.get(path,headers=login(client)).status_code==200

def test_role_boundaries_and_refresh(client):
    c=client;cashier=login(c,"cashier@gmail.com","cashier123")
    for path in ["/api/dashboard","/api/reports/daily","/api/admin/users","/api/stock/ingredients"]:
        assert c.get(path,headers=cashier).status_code==403
    assert c.post("/auth/refresh",headers=cashier).status_code==200
    assert c.post("/auth/refresh").status_code==401
    assert c.put("/api/orders/1",headers=cashier,json={"status":"ready"}).status_code==403

def test_existing_sqlite_upgrade_preserves_rows(tmp_path):
    path=tmp_path/"old.db";engine=create_engine("sqlite:///"+str(path))
    with engine.begin() as db:
        db.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(80), password_hash VARCHAR(255), role VARCHAR(20), full_name VARCHAR(120), active BOOLEAN, token_version INTEGER, created_at DATETIME)"))
        db.execute(text("INSERT INTO users VALUES (1,'existing','keep-hash','director','Existing',1,0,'2026-01-01')"))
    upgrade(engine);upgrade(engine)
    with engine.connect() as db:
        assert db.execute(text("SELECT password_hash FROM users WHERE id=1")).scalar()=="keep-hash"
        assert db.execute(text("SELECT updated_at FROM users WHERE id=1")).scalar()
        assert db.execute(text("SELECT count(*) FROM schema_versions")).scalar()==6
    assert len(list(tmp_path.glob("*.bak")))==1
    engine.dispose()

def test_printer_routing_and_failure(client,monkeypatch):
    from app.services.printers_services import print_order
    from types import SimpleNamespace as S
    department=S(name="Kitchen",printer_ip="192.168.1.80",printer_port=9100)
    order=S(order_number="B123",notes="",items=[S(quantity=2,menu_item=S(name="Tea",department=department),department_id=1)])
    order.items[0].menu_item.department_id=1
    mock=MagicMock()
    monkeypatch.setattr("app.services.printers_services.socket.create_connection",mock)
    assert print_order(order)[0]["status"]=="sent"
    assert b"2 x Tea" in mock.return_value.__enter__.return_value.sendall.call_args.args[0]
    mock.side_effect=OSError("offline")
    assert print_order(order)[0]["status"]=="failed"
    department.printer_ip=None
    assert print_order(order)[0]["status"]=="not_configured"

def test_backup_restore_and_production_settings(tmp_path):
    from app.ops import copy_database
    from app.config import Settings
    import sqlite3
    from contextlib import closing
    source=tmp_path/"source.db"
    with closing(sqlite3.connect(source)) as db:
        db.execute("CREATE TABLE saved (value TEXT)")
        db.execute("INSERT INTO saved VALUES ('preserved')")
        db.commit()
    backup=tmp_path/"backup.db"; restored=tmp_path/"restored.db"
    assert copy_database(source,backup)["integrity"]=="ok"
    result=copy_database(backup,restored)
    assert result["seconds"]<3600
    with closing(sqlite3.connect(restored)) as db:
        assert db.execute("SELECT value FROM saved").fetchone()[0]=="preserved"
    with pytest.raises(ValueError): copy_database(source,restored)
    with pytest.raises(ValueError): Settings(environment="production",secret_key="short",_env_file=None)
    assert Settings(environment="production",secret_key="a-unique-test-secret-with-more-than-32-chars",_env_file=None).environment=="production"

def test_pdf_pages_and_menu_persistence(client):
    from app.services.report_services import pdf_document
    from pypdf import PdfReader
    pdf=PdfReader(io.BytesIO(pdf_document(["A line "+str(n) for n in range(100)])))
    assert len(pdf.pages)==3 and "A line 99" in pdf.pages[2].extract_text()
    h=login(client);menu=new_menu(client,h)
    assert client.put(f'/api/admin/menu/{menu["id"]}',headers=h,json={"price":125.50}).status_code==200
    with TestClient(app) as fresh:
        items=fresh.get("/api/admin/menu",headers=login(fresh)).json()
        assert next(i for i in items if i["id"]==menu["id"])["price"]==125.50
    assert client.get("/api/reports/monthly?year=2026&month=2",headers=h).status_code==200


def test_business_day_boundaries_and_confirmed_revenue(client):
    from datetime import datetime
    from app.utils.helpers import date_window
    from app.models import Payment
    start,end=date_window(date(2026,9,24))
    assert start==datetime(2026,9,23,21) and end==datetime(2026,9,24,21)
    c=client;h=login(c);o=new_order(c,h)
    p=c.post(f'/api/orders/{o["id"]}/clear',headers=h,json={"expected_version":o["version"],"amount":320,"method":"cash"}).json()
    with SessionLocal() as db:
        payment=db.get(Payment,p["id"]);payment.completed_at=datetime(2026,9,23,21,30);db.commit()
    report=c.get("/api/reports/daily?date=2026-09-24",headers=h).json()
    assert report["restaurant"]["revenue"]>=320
    assert c.get("/api/payments/daily-summary?date=2026-09-24",headers=h).json()["date"]=="2026-09-24"

