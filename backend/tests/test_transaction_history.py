from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from app.main import app
from app.migrations import upgrade
from app.legacy_migrations import legacy_upgrade
from test_integration import login, new_menu, new_table


def test_rejected_payment_keeps_history_and_allows_safe_replacement():
    from test_integration import new_order
    with TestClient(app) as c:
        h = login(c)
        cashier = login(c, 'cashier@gmail.com', 'cashier123')
        order = new_order(c, h)
        path = f"/api/orders/{order['id']}"
        key = {**cashier, 'Idempotency-Key': uuid4().hex}
        data = {'expected_version': order['version'], 'amount': 320, 'method': 'm-pesa', 'reference': uuid4().hex}
        first = c.post(path + '/clear', headers=key, json=data)
        assert first.status_code == 201, first.text
        assert c.post(path + '/clear', headers=key, json=data).json() == first.json()
        assert c.post(path + '/clear', headers=key, json={**data, 'reference': 'OTHER'}).status_code == 409
        payment = first.json()
        assert payment['snapshot']['items'][0]['name'] == order['items'][0]['name']
        rejection = f"/api/payments/{payment['id']}/reject"
        assert c.post(rejection, headers=cashier, json={'reason': 'Incorrect reference'}).status_code == 403
        assert c.post(rejection, headers=h, json={'reason': '   '}).status_code == 422
        result = c.post(rejection, headers=h, json={'reason': 'Incorrect reference'})
        assert result.status_code == 200, result.text
        assert result.json()['status'] == 'rejected'
        assert c.put(f"/api/payments/{payment['id']}/verify", headers=cashier).status_code == 409
        current = c.get(path, headers=h).json()
        assert current['locked'] is False
        result = c.post(path + '/clear', headers={**cashier, 'Idempotency-Key': uuid4().hex},
                        json={'expected_version': current['version'], 'amount': 320, 'method': 'cash'})
        assert result.status_code == 201, result.text
        assert result.json()['id'] != payment['id']
        assert c.post(f"/api/payments/{result.json()['id']}/reject", headers=h, json={'reason': 'Do not reject confirmed money'}).status_code == 409
        history = c.get('/api/payments', headers=h).json()
        assert {p['status'] for p in history if p['order_id'] == order['id']} == {'completed', 'rejected'}


def test_stock_retry_is_one_ledger_movement():
    with TestClient(app) as c:
        h = login(c)
        item = c.post('/api/stock/ingredients', headers=h, json={'name': uuid4().hex, 'unit': 'kg', 'min_level': 0}).json()
        key = {**h, 'Idempotency-Key': uuid4().hex}
        data = {'ingredient_id': item['id'], 'quantity': 5, 'reason': 'Delivery'}
        first = c.post('/api/stock/add', headers=key, json=data)
        assert first.status_code == 201, first.text
        assert c.post('/api/stock/add', headers=key, json=data).json() == first.json()
        assert c.post('/api/stock/add', headers=key, json={**data, 'quantity': 6}).status_code == 409
        assert c.get(f"/api/stock/ingredients/{item['id']}", headers=h).json()['current_stock'] == 5


def test_original_payment_unique_constraint_is_migrated_without_losing_records(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'payments.db'))
    with engine.begin() as db:
        db.execute(text('CREATE TABLE payments (id INTEGER PRIMARY KEY, order_id INTEGER UNIQUE NOT NULL, amount FLOAT NOT NULL, method VARCHAR(20) NOT NULL, status VARCHAR(20) NOT NULL, notes VARCHAR(500), verified_by INTEGER, reference VARCHAR(100), created_at DATETIME NOT NULL, completed_at DATETIME)'))
        db.execute(text("INSERT INTO payments VALUES (7,12,116,'cash','completed',NULL,1,NULL,'2026-01-01','2026-01-01')"))
    upgrade(engine)
    upgrade(engine)
    with engine.begin() as db:
        assert db.execute(text('SELECT id,order_id,active_order_id,amount FROM payments')).one() == (7,12,12,116)
        db.execute(text("INSERT INTO payments (id,order_id,amount,method,status,created_at) VALUES (8,12,116,'m-pesa','rejected','2026-01-01')"))
    engine.dispose()


def test_menu_rename_preserves_bill_and_correction_destination():
    with TestClient(app) as c:
        h = login(c)
        menu = new_menu(c, h)
        other = new_menu(c, h)
        result = c.post('/api/orders', headers={**h, 'Idempotency-Key': uuid4().hex}, json={
            'table_id': new_table(c, h), 'items': [{'menu_item_id': menu['id'], 'quantity': 2}]})
        assert result.status_code == 201, result.text
        order = result.json()
        path = f"/api/orders/{order['id']}"
        result = c.put(f"/api/admin/menu/{menu['id']}", headers=h, json={
            'name': 'Renamed ' + uuid4().hex, 'department_id': other['department_id']})
        assert result.status_code == 200, result.text
        saved = c.get(path, headers=h).json()
        assert saved['items'][0]['name'] == menu['name']
        assert saved['items'][0]['department'] == menu['department']
        assert saved['items'][0]['historical_name_known'] is True
        result = c.post(path + '/change-requests', headers=h, json={
            'expected_version': saved['version'], 'kind': 'remove', 'reason': 'Customer changed quantity',
            'items': [{'order_item_id': saved['items'][0]['id'], 'quantity': 1}]})
        assert result.status_code == 201, result.text
        saved = c.get(path, headers=h).json()
        result = c.put(f"/api/order-change-requests/{saved['change_requests'][0]['id']}", headers=h,
                       json={'expected_version': saved['version'], 'decision': 'approved'})
        assert result.status_code == 200, result.text
        corrected = result.json()['batches'][-1]['items'][0]
        assert corrected['name'] == menu['name']
        assert corrected['department_id'] == menu['department_id']


def test_snapshot_upgrade_recovers_only_recorded_history(tmp_path):
    import json
    engine = create_engine('sqlite:///' + str(tmp_path / 'history.db'))
    legacy_upgrade(engine)  # a database created before Alembic
    with engine.begin() as db:
        db.execute(text('DELETE FROM schema_versions WHERE version=4'))
        db.execute(text("INSERT INTO order_items (id,order_id,menu_item_id,quantity,voided_quantity,price_at_time,ready,created_at) VALUES (101,1,1,1,0,116,0,CURRENT_TIMESTAMP),(102,1,1,1,0,116,0,CURRENT_TIMESTAMP)"))
        db.execute(text("INSERT INTO order_batches (order_id,kind,items,deliveries,created_by,created_at) VALUES (1,'original',:items,:deliveries,1,CURRENT_TIMESTAMP)"), {
            'items': json.dumps([{'order_item_id': 101, 'name': 'Original meal', 'department_id': 1}]),
            'deliveries': json.dumps([{'department_id': 1, 'department': 'Original kitchen'}])})
    upgrade(engine)
    upgrade(engine)
    with engine.connect() as db:
        assert db.execute(text('SELECT name_at_time,department_name_at_time FROM order_items WHERE id=101')).one() == ('Original meal', 'Original kitchen')
        assert db.execute(text('SELECT name_at_time FROM order_items WHERE id=102')).scalar() is None
    engine.dispose()
