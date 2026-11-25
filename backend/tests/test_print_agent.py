from conftest import waiter_headers
"""The branch print program: tickets wait on the server, the program collects, prints and reports."""
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Order
from app.models.waiter import OrderBatch
from test_integration import login, new_menu, new_table

spec = importlib.util.spec_from_file_location("print_agent", Path(__file__).parents[2] / "print-agent" / "print_agent.py")
agent = importlib.util.module_from_spec(spec); spec.loader.exec_module(agent)


class Through:
    """The program's server connection, going through the test client instead of the network."""
    def __init__(self, client, key):
        self.c, self.key = client, key

    def jobs(self):
        r = self.c.get('/api/print-agent/jobs', headers={'X-Print-Agent-Key': self.key}); r.raise_for_status(); return r.json()

    def report(self, result):
        r = self.c.post('/api/print-agent/results', headers={'X-Print-Agent-Key': self.key}, json=result); r.raise_for_status(); return r.json()


def order(c, h, menu):
    r = c.post('/api/orders', headers={**waiter_headers(c), 'Idempotency-Key': uuid4().hex},
               json={'table_id': new_table(c, h), 'items': [{'menu_item_id': menu['id'], 'quantity': 2}]})
    assert r.status_code == 201, r.text
    return r.json()


def status(batch_id):
    with SessionLocal() as db:
        return db.get(OrderBatch, batch_id).deliveries[0]['status']


def test_print_program_collects_prints_and_reports(monkeypatch):
    direct = MagicMock(side_effect=AssertionError('the cloud server must not print directly'))
    with TestClient(app) as c:
        director = login(c)
        menu = new_menu(c, director)
        c.post('/api/admin/printer-config', headers=director, json={'department_id': menu['department_id'], 'printer_ip': '192.168.1.60'})
        first = order(c, director, menu)
        with SessionLocal() as db:
            branch = db.get(Order, first['id']).branch_id
        assert c.post('/api/print-agents', headers=login(c, 'cashier@gmail.com', 'cashier123'), json={'branch_id': branch, 'name': 'x'}).status_code == 403
        made = c.post('/api/print-agents', headers=director, json={'branch_id': branch, 'name': 'Kitchen PC'})
        assert made.status_code == 201 and made.json()['key'].startswith('bpa_')
        key = made.json()['key']
        assert 'key' not in c.get('/api/print-agents', headers=director).json()[0]
        assert c.get('/api/print-agent/jobs', headers={'X-Print-Agent-Key': 'bpa_wrong'}).status_code == 401

        monkeypatch.setattr('app.services.printers_services.socket.create_connection', direct)
        bill = order(c, director, menu)
        batch = bill['batches'][0]['id']
        assert bill['batches'][0]['deliveries'][0]['status'] == 'queued'  # waiting for the program

        printed = []
        printer = lambda host, port, data: (printed.append((host, port, data)), ('sent', None))[1]
        server = Through(c, key)
        count, wait = agent.run_once(server, printer)
        assert count >= 1 and wait == 3 and status(batch) == 'sent'
        host, port, data = next(p for p in printed if menu['name'].encode('cp437') in p[2])
        assert (host, port) == ('192.168.1.60', 9100) and b'NEW ORDER' in data and b'2 x ' in data
        assert agent.run_once(server, printer)[0] == 0  # nothing is printed twice
        seen = next(a for a in c.get('/api/print-agents', headers=director).json() if a['name'] == 'Kitchen PC')
        assert seen['online'] and seen['last_seen']

        # Printer switched off: nothing printed, so the program tries again on its next check.
        again = order(c, director, menu)['batches'][0]['id']
        agent.run_once(server, lambda *a: ('not_sent', 'No route to host'))
        assert status(again) == 'queued'
        agent.run_once(server, printer)
        assert status(again) == 'sent'

        # The connection broke while printing: a manager decides, and the program prints the copy.
        broken = order(c, director, menu)['batches'][0]['id']
        agent.run_once(server, lambda *a: ('uncertain', 'Connection reset'))
        assert status(broken) == 'uncertain'
        assert agent.run_once(server, printer)[0] == 0
        r = c.post(f'/api/printer-jobs/{broken}/retry', headers={**director, 'Idempotency-Key': uuid4().hex},
                   json={'department_id': menu['department_id'], 'reason': 'Checked the kitchen', 'acknowledge_duplicate_risk': True})
        assert r.status_code == 200 and r.json()['status'] == 'queued'
        assert agent.run_once(server, printer)[0] == 1 and status(broken) == 'sent'

        # After the program is removed, the server prints directly again.
        assert c.delete(f"/api/print-agents/{made.json()['id']}", headers=director).status_code == 200
        assert c.get('/api/print-agent/jobs', headers={'X-Print-Agent-Key': key}).status_code == 401
        monkeypatch.setattr('app.services.printers_services.socket.create_connection', MagicMock(side_effect=OSError('offline')))
        assert order(c, director, menu)['batches'][0]['deliveries'][0]['status'] == 'not_sent'


def test_program_refuses_addresses_outside_the_local_network():
    assert agent.send('8.8.8.8', 9100, b'x')[0] == 'not_sent'
    assert agent.send('not-an-ip', 9100, b'x')[0] == 'not_sent'
