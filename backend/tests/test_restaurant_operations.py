from conftest import waiter_headers
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from test_integration import login, new_menu, new_table


def post(c, path, h, data):
    r = c.post(path, headers={**h, 'Idempotency-Key': uuid4().hex}, json=data)
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_opening_to_closing_day_and_stock_policy():
    with TestClient(app) as c:
        manager = login(c)
        cashier = login(c, 'cashier@gmail.com', 'cashier123')
        waiter = login(c, 'waiter@gmail.com', 'waiter123')
        menu = new_menu(c, manager, 116)
        stock = post(c, '/api/stock/ingredients', manager, {'name': uuid4().hex, 'unit': 'kg', 'current_stock': 10, 'min_level': 1})
        post(c, '/api/recipes', manager, {'menu_item_id': menu['id'], 'components': [{'ingredient_id': stock['id'], 'quantity': .5}]})
        shift = post(c, '/api/cashier/shifts', cashier, {'opening_float': 1000})
        order = post(c, '/api/orders', waiter, {'table_id': new_table(c, manager), 'items': [{'menu_item_id': menu['id'], 'quantity': 2}]})
        ingredient_path = f"/api/stock/ingredients/{stock['id']}"
        assert c.get(ingredient_path, headers=manager).json()['current_stock'] == 10
        assert c.post('/api/stock/deduct', headers=manager, json={'ingredient_id': stock['id'], 'quantity': 10}).status_code == 409
        line_id = order['items'][0]['id']
        path = f'/api/kitchen/lines/{line_id}'
        assert c.put(path, headers=waiter, json={'expected_version': 1, 'status': 'preparing'}).status_code == 403
        started = c.put(path, headers=manager, json={'expected_version': 1, 'status': 'preparing'})
        assert started.status_code == 200, started.text
        assert c.put(path, headers=manager, json={'expected_version': 1, 'status': 'preparing'}).status_code == 409
        assert c.get(ingredient_path, headers=manager).json()['current_stock'] == 9
        assert c.put(path, headers=manager, json={'expected_version': 2, 'status': 'ready'}).status_code == 200
        inbox = c.get('/api/notifications', headers=waiter).json()
        assert any(n['order_id'] == order['id'] for n in inbox)
        assert c.put(path, headers=waiter, json={'expected_version': 3, 'status': 'served'}).status_code == 200
        current = c.get(f"/api/orders/{order['id']}", headers=waiter).json()
        request = post(c, f"/api/orders/{order['id']}/change-requests", waiter, {
            'expected_version': current['version'], 'kind': 'remove', 'reason': 'One portion returned',
            'items': [{'order_item_id': line_id, 'quantity': 1}]})
        current = c.get(f"/api/orders/{order['id']}", headers=waiter).json()
        result = c.put(f"/api/order-change-requests/{current['change_requests'][0]['id']}", headers=manager, json={
            'expected_version': current['version'], 'decision': 'approved'})
        assert result.status_code == 200, result.text
        current = result.json()
        assert c.get(ingredient_path, headers=manager).json()['current_stock'] == 9
        assert any(w['order_item_id'] == line_id and w['quantity'] == 1 for w in c.get('/api/stock/food-waste', headers=manager).json())
        payment = post(c, f"/api/orders/{order['id']}/clear", cashier, {'expected_version': current['version'], 'amount': 116, 'method': 'cash', 'tendered_amount': 200})
        assert payment['change_amount'] == 84 and payment['shift_id'] == shift['id']
        refund_key = {**manager, 'Idempotency-Key': uuid4().hex}
        refund_body = {'amount': 16, 'reason': 'Service adjustment', 'shift_id': shift['id']}
        refund_url = f"/api/payments/{payment['id']}/refund"
        refund = c.post(refund_url, headers=refund_key, json=refund_body)
        assert refund.status_code == 201, refund.text
        assert c.post(refund_url, headers=refund_key, json=refund_body).json() == refund.json()
        assert c.post(refund_url, headers={**manager, 'Idempotency-Key': uuid4().hex}, json={**refund_body, 'amount': 101}).status_code == 409
        close_path = f"/api/cashier/shifts/{shift['id']}/close"
        assert c.post(close_path, headers=cashier, json={'counted_cash': 1090}).status_code == 400
        closed = post(c, close_path, cashier, {'counted_cash': 1100})
        assert closed['expected_cash'] == 1100 and closed['variance'] == 0
        reviewed = post(c, f"/api/cashier/shifts/{shift['id']}/review", manager, {})
        assert reviewed['status'] == 'reviewed'


def test_receiving_count_review_and_preparation_department_access():
    with TestClient(app) as c:
        manager = login(c, 'manager@gmail.com', 'manager123')
        director = login(c)
        ingredient = post(c, '/api/stock/ingredients', manager, {'name': uuid4().hex, 'unit': 'kg', 'min_level': 0})
        doc = post(c, '/api/stock/documents', manager, {'kind': 'receiving', 'reference': uuid4().hex, 'reason': 'Supplier delivery', 'lines': [{'ingredient_id': ingredient['id'], 'quantity': 12}]})
        posted = post(c, f"/api/stock/documents/{doc['id']}/post", manager, {})
        assert post(c, f"/api/stock/documents/{doc['id']}/post", manager, {}) == posted
        count = post(c, '/api/stock/documents', manager, {'kind': 'count', 'reference': uuid4().hex, 'reason': 'Closing stock count', 'lines': [{'ingredient_id': ingredient['id'], 'quantity': 11}]})
        assert c.post(f"/api/stock/documents/{count['id']}/post", headers=manager).status_code == 403
        assert post(c, f"/api/stock/documents/{count['id']}/post", director, {})['lines'][0]['delta'] == -1
        # There is no kitchen account any more (Majid, 2026-11-25).
        menu = new_menu(c, manager)
        r = c.post('/api/admin/users', headers=manager, json={'username': uuid4().hex + '@example.com', 'password': 'Kitchen123!', 'role': 'kitchen', 'department_id': menu['department_id']})
        assert r.status_code == 422


def test_purchase_partial_receipts_replay_and_over_receiving():
    with TestClient(app) as c:
        manager=login(c)
        store=login(c,'store@gmail.com','store123')
        ingredient=post(c,'/api/stock/ingredients',manager,{'name':uuid4().hex,'unit':'kg','min_level':0})
        supplier=post(c,'/api/suppliers',store,{'name':uuid4().hex})
        purchase=post(c,'/api/stock/documents',store,{'kind':'purchase','supplier_id':supplier['id'],'reference':uuid4().hex,'reason':'Weekly restock','lines':[{'ingredient_id':ingredient['id'],'quantity':10}]})
        path=f"/api/stock/documents/{purchase['id']}"
        assert c.post(path+'/post',headers=store).status_code==403
        assert post(c,path+'/post',manager,{})['status']=='approved'
        key={**store,'Idempotency-Key':uuid4().hex}
        delivery={'reference':uuid4().hex,'lines':[{'ingredient_id':ingredient['id'],'quantity':6}]}
        first=c.post(path+'/receive',headers=key,json=delivery)
        assert first.status_code==201,first.text
        assert c.post(path+'/receive',headers=key,json=delivery).json()==first.json()
        assert c.post(path+'/receive',headers={**store,'Idempotency-Key':uuid4().hex},json=delivery).status_code==409
        delivery['reference']=uuid4().hex
        assert c.post(path+'/receive',headers={**store,'Idempotency-Key':uuid4().hex},json=delivery).status_code==409
        delivery['lines'][0]['quantity']=4
        post(c,path+'/receive',store,delivery)
        assert c.get(f"/api/stock/ingredients/{ingredient['id']}",headers=store).json()['current_stock']==10
        saved=next(d for d in c.get('/api/stock/documents',headers=store).json() if d['id']==purchase['id'])
        assert saved['status']=='received'


def test_cancellation_before_preparation_releases_without_deduction():
    with TestClient(app) as c:
        h=login(c)
        menu=new_menu(c,h)
        ingredient=post(c,'/api/stock/ingredients',h,{'name':uuid4().hex,'unit':'kg','min_level':0,'current_stock':1})
        post(c,'/api/recipes',h,{'menu_item_id':menu['id'],'components':[{'ingredient_id':ingredient['id'],'quantity':1}]})
        order=post(c,'/api/orders',waiter_headers(c),{'table_id':new_table(c,h),'items':[{'menu_item_id':menu['id'],'quantity':1}]})
        assert c.delete(f"/api/orders/{order['id']}",headers=h).status_code==204
        post(c,'/api/stock/deduct',h,{'ingredient_id':ingredient['id'],'quantity':1,'reason':'Reservation released'})


def test_printer_recovery_does_not_repeat_network_send(monkeypatch):
    with TestClient(app) as c:
        h=login(c);menu=new_menu(c,h)
        order=post(c,'/api/orders',waiter_headers(c),{'table_id':new_table(c,h),'items':[{'menu_item_id':menu['id'],'quantity':1}]})
        post(c,'/api/admin/printer-config',h,{'department_id':menu['department_id'],'printer_ip':'192.168.1.80','printer_port':9100})
        from unittest.mock import Mock
        sender=Mock(return_value={'status':'uncertain','detail':'Connection interrupted'})
        monkeypatch.setattr('app.services.printers_services.send_batch_ticket',sender)
        path=f"/api/printer-jobs/{order['batches'][0]['id']}/retry"
        key={**h,'Idempotency-Key':uuid4().hex}
        payload={'department_id':menu['department_id'],'reason':'Operator checked station','acknowledge_duplicate_risk':True}
        first=c.post(path,headers=key,json=payload)
        assert first.status_code==200,first.text
        assert c.post(path,headers=key,json=payload).json()==first.json()
        assert sender.call_count==1


def test_receipt_reference_is_shared_between_wash_and_restaurant():
    from test_integration import new_order
    with TestClient(app) as c:
        h=login(c);order=new_order(c,h);reference=uuid4().hex.upper()
        post(c,f"/api/orders/{order['id']}/clear",h,{'expected_version':order['version'],'amount':order['total'],'method':'m-pesa','reference':reference})
        bay=post(c,'/api/carwash/bays',h,{'bay_number':int(uuid4().hex[:7],16),'name':'Test bay'})
        service=post(c,'/api/carwash/services',h,{'name':uuid4().hex,'price':500})
        body={'bay_id':bay['id'],'service_id':service['id'],'vehicle_plate':'KDA 123A','amount':500,'payment_method':'m-pesa','mpesa_reference':' '+reference.lower()+' '}
        assert c.post('/api/carwash/transaction',headers=h,json=body).status_code==409
        key={**h,'Idempotency-Key':uuid4().hex};body['mpesa_reference']=uuid4().hex
        first=c.post('/api/carwash/transaction',headers=key,json=body)
        assert first.status_code==201,first.text
        assert c.post('/api/carwash/transaction',headers=key,json=body).json()==first.json()


def test_concurrent_preparation_consumes_once():
    from concurrent.futures import ThreadPoolExecutor
    with TestClient(app) as c:
        h=login(c);menu=new_menu(c,h)
        ingredient=post(c,'/api/stock/ingredients',h,{'name':uuid4().hex,'unit':'kg','min_level':0,'current_stock':10})
        post(c,'/api/recipes',h,{'menu_item_id':menu['id'],'components':[{'ingredient_id':ingredient['id'],'quantity':2}]})
        order=post(c,'/api/orders',waiter_headers(c),{'table_id':new_table(c,h),'items':[{'menu_item_id':menu['id'],'quantity':1}]})
        path=f"/api/kitchen/lines/{order['items'][0]['id']}"
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(lambda _:c.put(path,headers=h,json={'expected_version':1,'status':'preparing'}),range(2)))
        assert sorted(r.status_code for r in responses)==[200,409]
        assert c.get(f"/api/stock/ingredients/{ingredient['id']}",headers=h).json()['current_stock']==8


def test_transfer_preserves_lines_and_notifies_new_waiter():
    from app.database import SessionLocal
    from app.models import User
    from sqlalchemy import select
    with TestClient(app) as c:
        h=login(c);menu=new_menu(c,h)
        order=post(c,'/api/orders',waiter_headers(c),{'table_id':new_table(c,h),'items':[{'menu_item_id':menu['id'],'quantity':1}]})
        with SessionLocal() as db: waiter_id=db.scalar(select(User.id).where(User.username=='waiter@gmail.com'))
        destination=new_table(c,h)
        transferred=post(c,f"/api/orders/{order['id']}/transfer",h,{'expected_version':order['version'],'table_id':destination,'waiter_id':waiter_id,'reason':'Service reassignment'})
        assert transferred['items']==order['items'] and transferred['waiter_id']==waiter_id and transferred['table_id']==destination
        tables=c.get('/api/tables',headers=h).json()
        assert next(t for t in tables if t['id']==order['table_id'])['occupied'] is False
        assert c.get('/ready').json()['status']=='ready'


def test_ingredients_leave_stock_when_the_bill_is_paid():
    """No kitchen screen (Majid, 2026-11-25): ingredients are held at order time and used at payment."""
    with TestClient(app) as c:
        manager = login(c)
        cashier = login(c, 'cashier@gmail.com', 'cashier123')
        waiter = waiter_headers(c)
        menu = new_menu(c, manager, 300)
        stock = post(c, '/api/stock/ingredients', manager, {'name': uuid4().hex, 'unit': 'kg', 'current_stock': 10, 'min_level': 0})
        post(c, '/api/recipes', manager, {'menu_item_id': menu['id'], 'components': [{'ingredient_id': stock['id'], 'quantity': .5}]})
        ingredient = f"/api/stock/ingredients/{stock['id']}"
        paid = post(c, '/api/orders', waiter, {'table_id': new_table(c, manager), 'items': [{'menu_item_id': menu['id'], 'quantity': 2}]})
        cancelled = post(c, '/api/orders', waiter, {'table_id': new_table(c, manager), 'items': [{'menu_item_id': menu['id'], 'quantity': 4}]})
        assert c.get(ingredient, headers=manager).json()['current_stock'] == 10  # held, not used yet
        # The manager moves the bill along the pipeline without a kitchen screen.
        assert c.put(f"/api/orders/{paid['id']}", headers=manager, json={'status': 'printed'}).status_code == 200
        assert c.delete(f"/api/orders/{cancelled['id']}", headers=manager).status_code in (200, 204)
        bill = c.get(f"/api/orders/{paid['id']}", headers=cashier).json()
        post(c, f"/api/orders/{paid['id']}/clear", cashier, {'expected_version': bill['version'], 'method': 'cash', 'amount': 600})
        assert c.get(ingredient, headers=manager).json()['current_stock'] == 9  # 2 dishes x 0.5 kg
        assert all(line['order_id'] != paid['id'] for line in c.get('/api/kitchen/lines', headers=manager).json())  # nothing left open
