"""Car-wash bay board, attendants, wash lifecycle and editing bays and services."""
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from test_integration import login


def _setup(c, h):
    bay = c.post("/api/carwash/bays", headers=h, json={"bay_number": int(uuid4().hex[:6], 16), "name": "Bay " + uuid4().hex[:4]}).json()
    service = c.post("/api/carwash/services", headers=h, json={"name": "Full wash " + uuid4().hex[:6], "price": 800}).json()
    attendant = c.post("/api/carwash/attendants", headers=h, json={"name": "Wanjiru " + uuid4().hex[:4], "phone": "0712000000"})
    assert attendant.status_code == 201, attendant.text
    return bay, service, attendant.json()


def _wash(c, h, bay, service, **extra):
    body = {"bay_id": bay["id"], "service_id": service["id"], "vehicle_plate": "KCB 100" + uuid4().hex[:1].upper(),
            "amount": service["price"], "payment_method": "cash"} | extra
    return c.post("/api/carwash/transaction", headers=h, json=body)


def test_wash_moves_through_the_bay_board_separately_from_payment():
    with TestClient(app) as c:
        manager = login(c, "carwash@gmail.com", "carwash123")
        cashier = login(c, "cashier@gmail.com", "cashier123")
        bay, service, attendant = _setup(c, manager)
        board = {b["id"]: b for b in c.get("/api/carwash/board", headers=cashier).json()}
        assert board[bay["id"]]["status"] == "free" and board[bay["id"]]["wash"] is None

        r = _wash(c, cashier, bay, service)
        assert r.status_code == 201, r.text
        wash = r.json()
        assert wash["wash_status"] == "waiting" and wash["payment_status"] == "completed"
        board = {b["id"]: b for b in c.get("/api/carwash/board", headers=cashier).json()}
        assert board[bay["id"]]["status"] == "waiting" and board[bay["id"]]["wash"]["id"] == wash["id"]
        assert _wash(c, cashier, bay, service).status_code == 409  # bay is busy

        path = f"/api/carwash/{wash['id']}/wash"
        assert c.put(path, headers=cashier, json={"status": "done"}).status_code == 409  # must start first
        assert c.put(path, headers=cashier, json={"status": "washing"}).status_code == 400  # needs an attendant
        r = c.put(path, headers=cashier, json={"status": "washing", "attendant_id": attendant["id"]})
        assert r.status_code == 200, r.text
        assert r.json()["wash_started_at"] and r.json()["attendant_id"] == attendant["id"]
        assert c.put(path, headers=cashier, json={"status": "washing"}).json()["wash_status"] == "washing"  # repeat is harmless
        board = {b["id"]: b for b in c.get("/api/carwash/board", headers=cashier).json()}
        assert board[bay["id"]]["status"] == "washing" and board[bay["id"]]["wash"]["attendant"] == attendant["name"]
        # Bays with a car cannot be closed.
        assert c.put(f"/api/carwash/bays/{bay['id']}", headers=manager, json={"is_active": False}).status_code == 409

        r = c.put(path, headers=cashier, json={"status": "done"})
        assert r.status_code == 200 and r.json()["wash_finished_at"]
        board = {b["id"]: b for b in c.get("/api/carwash/board", headers=cashier).json()}
        assert board[bay["id"]]["status"] == "free"
        assert _wash(c, cashier, bay, service).status_code == 201  # bay is free again

        # Pending M-Pesa payment does not block the wash, and finishing the wash does not confirm money.
        free_bay = c.post("/api/carwash/bays", headers=manager, json={"bay_number": int(uuid4().hex[:6], 16), "name": "Spare"}).json()
        pending = _wash(c, cashier, free_bay, service, payment_method="m-pesa", mpesa_reference="QW" + uuid4().hex[:8]).json()
        c.put(f"/api/carwash/{pending['id']}/wash", headers=cashier, json={"status": "washing", "attendant_id": attendant["id"]})
        done = c.put(f"/api/carwash/{pending['id']}/wash", headers=cashier, json={"status": "done"}).json()
        assert done["wash_status"] == "done" and done["payment_status"] == "pending"


def test_editing_bays_services_and_attendants():
    with TestClient(app) as c:
        manager = login(c, "carwash@gmail.com", "carwash123")
        cashier = login(c, "cashier@gmail.com", "cashier123")
        bay, service, attendant = _setup(c, manager)
        wash = _wash(c, cashier, bay, service).json()

        r = c.put(f"/api/carwash/services/{service['id']}", headers=manager, json={"price": 950, "duration_minutes": 45})
        assert r.status_code == 200 and r.json()["price"] == 950
        history = c.get("/api/carwash/history", headers=manager).json()["transactions"]
        assert next(x for x in history if x["id"] == wash["id"])["amount"] == 800  # old washes keep their price
        assert c.put(f"/api/carwash/services/{service['id']}", headers=cashier, json={"price": 1}).status_code == 403
        assert c.put(f"/api/carwash/services/{service['id']}", headers=manager, json={"price": 10.555}).status_code == 422

        other = c.post("/api/carwash/bays", headers=manager, json={"bay_number": int(uuid4().hex[:6], 16), "name": "Other"}).json()
        assert c.put(f"/api/carwash/bays/{other['id']}", headers=manager, json={"bay_number": bay["bay_number"]}).status_code == 409
        r = c.put(f"/api/carwash/bays/{other['id']}", headers=manager, json={"name": "Jet wash", "is_active": False})
        assert r.status_code == 200 and r.json()["name"] == "Jet wash" and r.json()["is_active"] is False
        assert other["id"] not in {b["id"] for b in c.get("/api/carwash/board", headers=manager).json()}

        r = c.put(f"/api/carwash/attendants/{attendant['id']}", headers=manager, json={"is_active": False})
        assert r.status_code == 200 and r.json()["is_active"] is False
        assert c.put(f"/api/carwash/{wash['id']}/wash", headers=cashier,
                     json={"status": "washing", "attendant_id": attendant["id"]}).status_code == 400
        assert c.post("/api/carwash/attendants", headers=cashier, json={"name": "Nope"}).status_code == 403
