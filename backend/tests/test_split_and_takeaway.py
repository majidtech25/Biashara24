from conftest import waiter_headers
"""Takeaway orders, splitting a bill by items, and paying one bill in parts."""
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from test_integration import login, new_menu, new_table


def send(c, method, path, h, data=None, status=(200, 201)):
    r = c.request(method, path, headers={**h, 'Idempotency-Key': uuid4().hex}, json=data)
    assert r.status_code in status, r.text
    return r.json()


def order(c, h, items, **extra):
    body = {'items': [{'menu_item_id': m['id'], 'quantity': q} for m, q in items], **extra}
    if 'order_type' not in extra:
        body['table_id'] = new_table(c, h)
    return send(c, 'POST', '/api/orders', waiter_headers(c), body)


def test_takeaway_orders_need_no_table():
    with TestClient(app) as c:
        waiter = login(c, 'waiter@gmail.com', 'waiter123')
        director = login(c)
        tea = new_menu(c, director, 100)
        bill = order(c, waiter, [(tea, 2)], order_type='takeaway', customer='Amina')
        assert bill['order_type'] == 'takeaway' and bill['table_id'] is None and bill['total'] == 200 and bill['customer'] == 'Amina'
        r = c.post('/api/orders', headers={**waiter, 'Idempotency-Key': uuid4().hex},
                   json={'order_type': 'takeaway', 'table_id': new_table(c, director), 'items': [{'menu_item_id': tea['id'], 'quantity': 1}]})
        assert r.status_code == 422
        r = c.post('/api/orders', headers={**waiter, 'Idempotency-Key': uuid4().hex}, json={'items': [{'menu_item_id': tea['id'], 'quantity': 1}]})
        assert r.status_code == 422
        cashier = login(c, 'cashier@gmail.com', 'cashier123')
        paid = send(c, 'POST', f"/api/orders/{bill['id']}/clear", cashier, {'expected_version': bill['version'], 'amount': 200, 'method': 'cash'})
        assert paid['status'] == 'completed'
        assert c.get(f"/api/orders/{bill['id']}", headers=cashier).json()['status'] == 'cleared'


def test_splitting_a_bill_moves_items_kitchen_state_and_reserved_stock():
    with TestClient(app) as c:
        director = login(c)
        chips, soda = new_menu(c, director, 150), new_menu(c, director, 80)
        potato = send(c, 'POST', '/api/stock/ingredients', director, {'name': 'Potato ' + uuid4().hex[:6], 'unit': 'kg', 'current_stock': 10, 'min_level': 0})
        send(c, 'POST', '/api/recipes', director, {'menu_item_id': chips['id'], 'components': [{'ingredient_id': potato['id'], 'quantity': 0.3}]})
        bill = order(c, director, [(chips, 3), (soda, 2)])
        chips_line, soda_line = bill['items'][0]['id'], bill['items'][1]['id']
        r = send(c, 'POST', f"/api/orders/{bill['id']}/split", director, {'expected_version': bill['version'], 'customer': 'Brian',
                 'items': [{'order_item_id': chips_line, 'quantity': 1}, {'order_item_id': soda_line, 'quantity': 2}]})
        original, new = r['original'], r['new']
        assert original['total'] == 300 and new['total'] == 310 and new['split_from_id'] == bill['id'] and new['customer'] == 'Brian'
        assert new['table_id'] == bill['table_id'] and new['order_number'] != bill['order_number']
        assert sorted((i['name'], i['quantity']) for i in new['items']) == sorted([(chips['name'], 1), (soda['name'], 2)])
        assert [(i['id'], i['quantity']) for i in original['items']] == [(chips_line, 2)]
        # Stock reserved for the chips is split too: preparing each bill takes its own share.
        new_chips = next(i['id'] for i in new['items'] if i['name'] == chips['name'])
        assert send(c, 'PUT', f'/api/kitchen/lines/{new_chips}', director, {'expected_version': 1, 'status': 'preparing'})
        assert c.get(f"/api/stock/ingredients/{potato['id']}", headers=director).json()['current_stock'] == 9.7
        assert send(c, 'PUT', f'/api/kitchen/lines/{chips_line}', director, {'expected_version': 2, 'status': 'preparing'})
        assert c.get(f"/api/stock/ingredients/{potato['id']}", headers=director).json()['current_stock'] == 9.1
        # Old versions, everything at once, or too much are refused.
        r = c.post(f"/api/orders/{bill['id']}/split", headers=director, json={'expected_version': bill['version'], 'items': [{'order_item_id': chips_line, 'quantity': 1}]})
        assert r.status_code == 409
        current = c.get(f"/api/orders/{bill['id']}", headers=director).json()
        r = c.post(f"/api/orders/{bill['id']}/split", headers=director, json={'expected_version': current['version'], 'items': [{'order_item_id': chips_line, 'quantity': 2}]})
        assert r.status_code == 400 and 'Leave at least one item' in r.json()['detail']
        r = c.post(f"/api/orders/{bill['id']}/split", headers=director, json={'expected_version': current['version'], 'items': [{'order_item_id': chips_line, 'quantity': 3}]})
        assert r.status_code == 400


def test_one_bill_paid_in_parts_by_cash_and_mpesa():
    with TestClient(app) as c:
        director = login(c)
        cashier = login(c, 'cashier@gmail.com', 'cashier123')
        meal = new_menu(c, director, 1000)
        bill = order(c, director, [(meal, 1)])
        path = f"/api/orders/{bill['id']}/clear"
        # A smaller amount is refused unless the cashier marks it as a part payment.
        r = c.post(path, headers=cashier, json={'expected_version': bill['version'], 'amount': 600, 'method': 'cash'})
        assert r.status_code == 400
        first = send(c, 'POST', path, cashier, {'expected_version': bill['version'], 'amount': 600, 'method': 'cash',
                     'tendered_amount': 1000, 'part_payment': True})
        assert first['status'] == 'completed' and first['change_amount'] == 400
        current = c.get(f"/api/orders/{bill['id']}", headers=cashier).json()
        assert current['status'] != 'cleared' and current['paid_amount'] == 600 and current['balance'] == 400 and current['locked']
        r = c.post(path, headers=cashier, json={'expected_version': current['version'], 'amount': 500, 'method': 'cash', 'part_payment': True})
        assert r.status_code == 400 and '400.00 is left' in r.json()['detail']
        receipt = 'Q' + uuid4().hex[:9].upper()
        second = send(c, 'POST', path, cashier, {'expected_version': current['version'], 'amount': 400, 'method': 'm-pesa', 'reference': receipt})
        assert second['status'] == 'pending'
        current = c.get(f"/api/orders/{bill['id']}", headers=cashier).json()
        assert current['status'] == 'payment_pending' and current['balance'] == 0 and current['awaiting_confirmation'] == 400
        assert c.post(path, headers=cashier, json={'expected_version': current['version'], 'amount': 1, 'method': 'cash', 'part_payment': True}).status_code == 409
        send(c, 'PUT', f"/api/payments/{second['id']}/verify", cashier)
        current = c.get(f"/api/orders/{bill['id']}", headers=cashier).json()
        assert current['status'] == 'cleared' and current['paid_amount'] == 1000
        assert [(p['amount'], p['method']) for p in current['payments']] == [(600, 'cash'), (400, 'm-pesa')]
        # Item sales are counted once for the bill, not once per payment.
        sold = [i for i in c.get('/api/reports/profit-vat', headers=director).json()['items'] if i['item'] == meal['name']]
        assert [(i['quantity'], i['gross']) for i in sold] == [(1, 1000)]


def test_rejecting_a_part_payment_reopens_the_balance():
    with TestClient(app) as c:
        director = login(c)
        meal = new_menu(c, director, 500)
        bill = order(c, director, [(meal, 1)])
        path = f"/api/orders/{bill['id']}/clear"
        part = send(c, 'POST', path, director, {'expected_version': bill['version'], 'amount': 200, 'method': 'm-pesa',
                    'reference': 'Q' + uuid4().hex[:9].upper(), 'part_payment': True})
        status_before = c.get(f"/api/orders/{bill['id']}", headers=director).json()['status']
        send(c, 'POST', f"/api/payments/{part['id']}/reject", director, {'reason': 'Receipt not found'})
        current = c.get(f"/api/orders/{bill['id']}", headers=director).json()
        assert current['balance'] == 500 and current['status'] == status_before and not current['locked']
        send(c, 'POST', path, director, {'expected_version': current['version'], 'amount': 500, 'method': 'cash'})
        assert c.get(f"/api/orders/{bill['id']}", headers=director).json()['status'] == 'cleared'
