"""Profit and VAT report: VAT taken out of inclusive prices, food cost from preparation,
credit notes, and stock written off. Other tests share the database, so the checks
compare the report before and after this test's own sales."""
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from test_integration import login, new_menu, new_table


def post(c, path, h, data):
    r = c.post(path, headers={**h, 'Idempotency-Key': uuid4().hex}, json=data)
    assert r.status_code in (200, 201), r.text
    return r.json()


def report(c, h):
    r = c.get('/api/reports/profit-vat', headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_profit_and_vat_for_a_sold_dish():
    with TestClient(app) as c:
        director = login(c)
        before = report(c, director)
        menu = new_menu(c, director, 580)  # 500 + 16% VAT
        beef = post(c, '/api/stock/ingredients', director, {'name': 'Beef ' + uuid4().hex[:6], 'unit': 'kg',
                    'current_stock': 10, 'min_level': 1, 'cost_per_unit': 200})
        post(c, '/api/recipes', director, {'menu_item_id': menu['id'], 'components': [{'ingredient_id': beef['id'], 'quantity': 0.5}]})
        order = post(c, '/api/orders', director, {'table_id': new_table(c, director), 'items': [{'menu_item_id': menu['id'], 'quantity': 2}]})
        line = order['items'][0]['id']
        r = c.put(f'/api/kitchen/lines/{line}', headers=director, json={'expected_version': 1, 'status': 'preparing'})
        assert r.status_code == 200, r.text
        # A later price change does not change the cost of food already prepared.
        assert c.put(f"/api/stock/ingredients/{beef['id']}", headers=director, json={'cost_per_unit': 999}).json()['cost_per_unit'] == 999
        order = c.get(f"/api/orders/{order['id']}", headers=director).json()
        payment = post(c, f"/api/orders/{order['id']}/clear", director, {'expected_version': order['version'], 'amount': 1160,
                       'method': 'm-pesa', 'reference': 'Q' + uuid4().hex[:9].upper()})
        assert c.put(f"/api/payments/{payment['id']}/verify", headers=director).status_code == 200
        post(c, f"/api/payments/{payment['id']}/refund", director, {'amount': 116, 'reason': 'Cold food',
             'reference': 'R' + uuid4().hex[:9].upper()})
        waste = post(c, '/api/stock/documents', director, {'kind': 'wastage', 'reference': uuid4().hex, 'reason': 'Spoiled',
                     'lines': [{'ingredient_id': beef['id'], 'quantity': 0.25}]})
        post(c, f"/api/stock/documents/{waste['id']}/post", director, {})

        after = report(c, director)
        # Daily reports and the dashboard still work after a refund (they used to fail with a type error).
        assert c.get('/api/reports/daily', headers=director).status_code == 200
        assert c.get('/api/dashboard', headers=director).status_code == 200
        delta = lambda section, key: round(after[section][key] - before[section][key], 2)
        assert delta('restaurant', 'sales_gross') == 1160
        assert delta('restaurant', 'sales_vat') == 160
        assert delta('restaurant', 'refunds_gross') == 116 and delta('restaurant', 'refunds_vat') == 16
        assert delta('restaurant', 'net_sales') == 900          # 1000 net sales - 100 net refund
        assert delta('restaurant', 'food_cost') == 200          # 1 kg of beef at 200
        assert delta('restaurant', 'gross_profit') == 700
        assert delta('vat', 'vat_due') == 144                   # 160 output VAT - 16 on the credit note
        assert delta('restaurant', 'stock_written_off') == round(0.25 * 999, 2)  # wasted after the price change
        item = next(i for i in after['items'] if i['item'] == menu['name'])
        assert item == {'item': menu['name'], 'quantity': 2, 'gross': 1160, 'net': 1000, 'food_cost': 200,
                        'gross_profit': 800, 'units_without_cost': 0}
        rate = next(r for r in after['vat']['rates'] if r['rate'] == 16)
        assert round(rate['gross'] - rate['vat'], 2) == rate['net']


def test_profit_report_is_for_managers_and_checks_dates():
    with TestClient(app) as c:
        cashier = login(c, 'cashier@gmail.com', 'cashier123')
        director = login(c)
        assert c.get('/api/reports/profit-vat', headers=cashier).status_code == 403
        assert c.get('/api/reports/profit-vat?from_date=2026-11-02&to_date=2026-11-01', headers=director).status_code == 400
