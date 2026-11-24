"""Packs (unit conversion), delivery prices, expiry batches and supplier returns."""
from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.utils.helpers import business_today
from test_integration import login


def post(c, path, h, data, status=(200, 201)):
    r = c.post(path, headers={**h, 'Idempotency-Key': uuid4().hex}, json=data)
    assert r.status_code in status, r.text
    return r.json()


def ingredient(c, h, unit='kg', cost=0):
    return post(c, '/api/stock/ingredients', h, {'name': 'Item ' + uuid4().hex[:8], 'unit': unit, 'min_level': 0, 'cost_per_unit': cost})


def document(c, h, kind, lines, supplier_id=None):
    doc = post(c, '/api/stock/documents', h, {'kind': kind, 'reference': uuid4().hex[:12], 'reason': 'Test ' + kind,
               'supplier_id': supplier_id, 'lines': lines})
    return post(c, f"/api/stock/documents/{doc['id']}/post", h, {})


def stock(c, h, item):
    return c.get(f"/api/stock/ingredients/{item['id']}", headers=h).json()


def test_deliveries_in_packs_set_the_cost_per_stock_unit():
    with TestClient(app) as c:
        manager = login(c, 'manager@gmail.com', 'manager123')
        flour = ingredient(c, manager)
        flour = post(c, f"/api/stock/ingredients/{flour['id']}/packs", manager, {'name': '50 kg bag', 'factor': 50})
        assert flour['packs'][0]['name'] == '50 kg bag' and flour['packs'][0]['factor'] == 50
        assert c.post(f"/api/stock/ingredients/{flour['id']}/packs", headers=manager, json={'name': '50 KG BAG', 'factor': 2}).status_code == 409
        posted = document(c, manager, 'receiving', [{'ingredient_id': flour['id'], 'quantity': 2, 'pack': '50 kg bag', 'unit_cost': 4500}])
        line = posted['lines'][0]
        assert line['quantity'] == 100 and line['pack_quantity'] == 2 and line['unit_cost'] == 90
        now = stock(c, manager, flour)
        assert now['current_stock'] == 100 and now['cost_per_unit'] == 90
        # Counts can be entered in packs too.
        director = login(c)
        count = post(c, '/api/stock/documents', manager, {'kind': 'count', 'reference': uuid4().hex[:12], 'reason': 'Monthly count',
                     'lines': [{'ingredient_id': flour['id'], 'quantity': 1.5, 'pack': '50 kg bag'}]})
        assert post(c, f"/api/stock/documents/{count['id']}/post", director, {})['lines'][0]['delta'] == -25
        # Unknown packs and prices on the wrong document are refused.
        r = c.post('/api/stock/documents', headers={**manager, 'Idempotency-Key': uuid4().hex}, json={'kind': 'receiving',
                   'reference': 'x', 'reason': 'Bad pack', 'lines': [{'ingredient_id': flour['id'], 'quantity': 1, 'pack': 'crate'}]})
        assert r.status_code == 400 and 'no pack called' in r.json()['detail']
        r = c.post('/api/stock/documents', headers={**manager, 'Idempotency-Key': uuid4().hex}, json={'kind': 'wastage',
                   'reference': 'x', 'reason': 'Bad price', 'lines': [{'ingredient_id': flour['id'], 'quantity': 1, 'unit_cost': 3}]})
        assert r.status_code == 400
        removed = c.delete(f"/api/stock/ingredients/{flour['id']}/packs/{flour['packs'][0]['id']}", headers=manager)
        assert removed.status_code == 200 and removed.json()['packs'] == []


def test_stock_with_expiry_dates_is_used_soonest_first():
    with TestClient(app) as c:
        manager = login(c, 'manager@gmail.com', 'manager123')
        milk = ingredient(c, manager, 'litre', 100)
        today = business_today()
        document(c, manager, 'receiving', [{'ingredient_id': milk['id'], 'quantity': 10, 'expiry_date': str(today + timedelta(days=20))}])
        document(c, manager, 'receiving', [{'ingredient_id': milk['id'], 'quantity': 6, 'expiry_date': str(today + timedelta(days=2))}])
        expiring = [b for b in c.get('/api/stock/expiry?days=7', headers=manager).json() if b['ingredient_id'] == milk['id']]
        assert [(b['remaining'], b['days_left'], b['status']) for b in expiring] == [(6, 2, 'expiring')]
        assert expiring[0]['value'] == 600
        # Using 8 litres empties the batch expiring first and takes 2 from the next.
        assert c.post('/api/stock/deduct', headers=manager, json={'ingredient_id': milk['id'], 'quantity': 8}).status_code == 200
        assert [b for b in c.get('/api/stock/expiry?days=7', headers=manager).json() if b['ingredient_id'] == milk['id']] == []
        later = [b for b in c.get('/api/stock/expiry?days=30', headers=manager).json() if b['ingredient_id'] == milk['id']]
        assert [b['remaining'] for b in later] == [8]
        # Expiry dates belong on deliveries.
        r = c.post('/api/stock/documents', headers={**manager, 'Idempotency-Key': uuid4().hex}, json={'kind': 'wastage', 'reference': 'x',
                   'reason': 'Spoiled', 'lines': [{'ingredient_id': milk['id'], 'quantity': 1, 'expiry_date': str(today)}]})
        assert r.status_code == 400
        cashier = login(c, 'cashier@gmail.com', 'cashier123')
        assert c.get('/api/stock/expiry', headers=cashier).status_code == 403


def test_returning_stock_to_a_supplier():
    with TestClient(app) as c:
        manager = login(c, 'manager@gmail.com', 'manager123')
        director = login(c)
        supplier = post(c, '/api/suppliers', director, {'name': 'Supplier ' + uuid4().hex[:6], 'contact': '0700000000'})
        eggs = ingredient(c, manager, 'piece', 15)
        eggs = post(c, f"/api/stock/ingredients/{eggs['id']}/packs", manager, {'name': 'tray', 'factor': 30})
        document(c, manager, 'receiving', [{'ingredient_id': eggs['id'], 'quantity': 4, 'pack': 'tray'}], supplier['id'])
        r = c.post('/api/stock/documents', headers={**manager, 'Idempotency-Key': uuid4().hex}, json={'kind': 'return', 'reference': 'RET-1',
                   'reason': 'Cracked tray', 'lines': [{'ingredient_id': eggs['id'], 'quantity': 1, 'pack': 'tray'}]})
        assert r.status_code == 400 and 'supplier' in r.json()['detail']
        returned = document(c, manager, 'return', [{'ingredient_id': eggs['id'], 'quantity': 1, 'pack': 'tray'}], supplier['id'])
        assert returned['kind'] == 'return' and returned['supplier_id'] == supplier['id'] and returned['lines'][0]['delta'] == -30
        assert stock(c, manager, eggs)['current_stock'] == 90
        moves = c.get(f"/api/stock/ingredients/{eggs['id']}", headers=manager).json()['transactions']
        assert moves[0]['type'] == 'deduction' and moves[0]['quantity'] == 30


def test_purchase_price_carries_to_the_delivery():
    with TestClient(app) as c:
        director = login(c)
        supplier = post(c, '/api/suppliers', director, {'name': 'Supplier ' + uuid4().hex[:6], 'contact': ''})
        oil = ingredient(c, director, 'litre', 200)
        oil = post(c, f"/api/stock/ingredients/{oil['id']}/packs", director, {'name': '20 litre jerrycan', 'factor': 20})
        purchase = post(c, '/api/stock/documents', director, {'kind': 'purchase', 'reference': uuid4().hex[:10], 'reason': 'Weekly order',
                        'supplier_id': supplier['id'], 'lines': [{'ingredient_id': oil['id'], 'quantity': 2, 'pack': '20 litre jerrycan', 'unit_cost': 5000}]})
        post(c, f"/api/stock/documents/{purchase['id']}/post", director, {})
        assert c.post(f"/api/stock/documents/{purchase['id']}/receive", headers={**director, 'Idempotency-Key': uuid4().hex},
                      json={'reference': uuid4().hex[:8], 'lines': [{'ingredient_id': oil['id'], 'quantity': 3, 'pack': '20 litre jerrycan'}]}).status_code == 409
        receipt = post(c, f"/api/stock/documents/{purchase['id']}/receive", director,
                       {'reference': uuid4().hex[:8], 'lines': [{'ingredient_id': oil['id'], 'quantity': 1, 'pack': '20 litre jerrycan',
                                                                  'expiry_date': str(business_today() + timedelta(days=90))}]})
        assert receipt['lines'][0]['quantity'] == 20 and receipt['lines'][0]['unit_cost'] == 250
        assert stock(c, director, oil)['cost_per_unit'] == 250
        assert any(b['ingredient_id'] == oil['id'] for b in c.get('/api/stock/expiry?days=120', headers=director).json())
