"""Printers per branch, and the background retry of tickets that were never sent."""
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Order
from app.models.waiter import OrderBatch
from app.services.printers_services import RETRY_LIMIT, retry_unsent
from test_integration import login, new_menu, new_table


def new_order(c, h, menu):
    r = c.post('/api/orders', headers={**h, 'Idempotency-Key': uuid4().hex},
               json={'table_id': new_table(c, h), 'items': [{'menu_item_id': menu['id'], 'quantity': 1}]})
    assert r.status_code == 201, r.text
    return r.json()


class Printer:
    """Stands in for the network: records where tickets go, and can be unreachable."""
    def __init__(self):
        self.reachable, self.sent_to = True, []

    def __call__(self, address, timeout):
        if not self.reachable:
            raise OSError('No route to host')
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.sendall.side_effect = lambda data: self.sent_to.append(address)
        return conn


def test_branch_printer_is_used_instead_of_the_department_printer(monkeypatch):
    printer = Printer()
    monkeypatch.setattr('app.services.printers_services.socket.create_connection', printer)
    with TestClient(app) as c:
        director = login(c)
        menu = new_menu(c, director)
        assert c.post('/api/admin/printer-config', headers=director, json={'department_id': menu['department_id'],
                      'printer_ip': '192.168.1.10'}).status_code == 200
        first = new_order(c, director, menu)
        with SessionLocal() as db:
            branch_id = db.get(Order, first['id']).branch_id
        assert printer.sent_to[-1] == ('192.168.1.10', 9100)
        bad = c.put('/api/admin/branch-printers', headers=director, json={'branch_id': branch_id, 'department_id': menu['department_id'],
                    'printer_ip': '8.8.8.8'})
        assert bad.status_code == 422
        saved = c.put('/api/admin/branch-printers', headers=director, json={'branch_id': branch_id, 'department_id': menu['department_id'],
                      'printer_ip': '10.0.5.20', 'printer_port': 9101})
        assert saved.status_code == 200, saved.text
        assert saved.json()['printer_ip'] == '10.0.5.20' and saved.json()['department'] == menu['department']
        new_order(c, director, menu)
        assert printer.sent_to[-1] == ('10.0.5.20', 9101)
        assert any(p['id'] == saved.json()['id'] for p in c.get('/api/admin/branch-printers', headers=director).json())
        cashier = login(c, 'cashier@gmail.com', 'cashier123')
        assert c.get('/api/admin/branch-printers', headers=cashier).status_code == 403
        assert c.delete(f"/api/admin/branch-printers/{saved.json()['id']}", headers=director).status_code == 204
        new_order(c, director, menu)
        assert printer.sent_to[-1] == ('192.168.1.10', 9100)


def test_unreachable_printer_is_retried_in_the_background_but_uncertain_tickets_are_not(monkeypatch):
    printer = Printer()
    monkeypatch.setattr('app.services.printers_services.socket.create_connection', printer)
    with TestClient(app) as c:
        director = login(c)
        menu = new_menu(c, director)
        c.post('/api/admin/printer-config', headers=director, json={'department_id': menu['department_id'], 'printer_ip': '192.168.1.11'})
        printer.reachable = False
        order = new_order(c, director, menu)
        state = order['batches'][0]['deliveries'][0]
        assert state['status'] == 'not_sent'
        with SessionLocal() as db:
            for _ in range(RETRY_LIMIT + 2):  # still unreachable: tries stop at the limit
                retry_unsent(db)
            batch = db.get(OrderBatch, order['batches'][0]['id'])
            assert batch.deliveries[0]['status'] == 'not_sent' and batch.deliveries[0]['attempts'] == RETRY_LIMIT

        printer.reachable = False
        second = new_order(c, director, menu)
        printer.reachable = True
        with SessionLocal() as db:
            assert retry_unsent(db) >= 1
            batch = db.get(OrderBatch, second['batches'][0]['id'])
            assert batch.deliveries[0]['status'] == 'sent' and batch.deliveries[0]['attempts'] == 2
            # A ticket that may have printed is left for staff to decide.
            third = new_order(c, director, menu)
            batch = db.get(OrderBatch, third['batches'][0]['id'])
            batch.deliveries = [{**batch.deliveries[0], 'status': 'uncertain'}]
            db.commit()
            before = len(printer.sent_to)
            retry_unsent(db)
            assert len(printer.sent_to) == before
