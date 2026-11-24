"""Branch isolation: each branch sees only its own tables, bills, money and stock."""
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from test_integration import login, new_menu


def _user(c, director, role, branch_id):
    username = f"{role}-{uuid4().hex[:8]}@example.com"
    r = c.post("/api/admin/users", headers=director,
               json={"username": username, "password": "Password123!", "role": role, "branch_id": branch_id})
    assert r.status_code == 201, r.text
    assert r.json()["branch_id"] == branch_id
    return login(c, username, "Password123!")


def test_branches_keep_records_separate():
    with TestClient(app) as c:
        director = login(c)
        main_manager = login(c, "manager@gmail.com", "manager123")
        main_waiter = login(c, "waiter@gmail.com", "waiter123")
        code = "B" + uuid4().hex[:6]
        r = c.post("/api/branches", headers=director, json={"name": "Branch " + code, "code": code, "address": "Westlands"})
        assert r.status_code == 201, r.text
        branch = r.json()
        try:
            assert c.post("/api/branches", headers=main_manager, json={"name": "Nope", "code": "NOPE"}).status_code == 403
            manager = _user(c, director, "manager", branch["id"])
            waiter = _user(c, director, "waiter", branch["id"])
            cashier = _user(c, director, "cashier", branch["id"])
            # Managers cannot place staff in another branch.
            r = c.post("/api/admin/users", headers=manager, json={"username": "x-" + uuid4().hex[:8], "password": "Password123!",
                                                                 "role": "waiter", "branch_id": 1})
            assert r.status_code == 403
            # With two active branches, a director working across all of them must choose one.
            assert c.post("/api/tables", headers=director, json={"number": 9001}).status_code == 400
            in_branch = {**director, "X-Branch-Id": str(branch["id"])}

            # Table numbers only need to be unique within a branch.
            main_numbers = {t["number"] for t in c.get("/api/tables", headers=main_manager).json()}
            number = min(main_numbers) if main_numbers else 1
            r = c.post("/api/tables", headers=manager, json={"number": number})
            assert r.status_code == 201, r.text
            table = r.json()["id"]
            assert table not in {t["id"] for t in c.get("/api/tables", headers=main_manager).json()}

            item = new_menu(c, in_branch, 250)  # one shared menu
            assert item["id"] in {m["id"] for m in c.get("/api/menu", headers=waiter).json()}
            r = c.post("/api/orders", headers={**waiter, "Idempotency-Key": uuid4().hex},
                       json={"table_id": table, "items": [{"menu_item_id": item["id"], "quantity": 2}]})
            assert r.status_code == 201, r.text
            bill = r.json()

            # Other branches cannot see the bill; the director sees it when looking at this branch or all.
            assert c.get(f"/api/orders/{bill['id']}", headers=main_manager).status_code == 404
            assert bill["id"] not in {o["id"] for o in c.get("/api/orders", headers=main_manager).json()}
            assert c.get(f"/api/orders/{bill['id']}", headers=in_branch).status_code == 200
            assert c.get(f"/api/orders/{bill['id']}", headers=director).status_code == 200
            assert c.get(f"/api/orders/{bill['id']}", headers={**director, "X-Branch-Id": "1"}).status_code == 404
            assert c.get("/api/orders", headers={**director, "X-Branch-Id": "999999"}).status_code == 400

            # Switching a menu item off at this branch hides it here only.
            r = c.put(f"/api/branches/{branch['id']}/menu/{item['id']}", headers=manager, json={"available": False})
            assert r.status_code == 200, r.text
            assert c.put(f"/api/branches/1/menu/{item['id']}", headers=manager, json={"available": False}).status_code == 403
            assert item["id"] not in {m["id"] for m in c.get("/api/menu", headers=waiter).json()}
            assert item["id"] in {m["id"] for m in c.get("/api/menu", headers=main_waiter).json()}
            r = c.post(f"/api/orders/{bill['id']}/items", headers={**waiter, "Idempotency-Key": uuid4().hex},
                       json={"expected_version": bill["version"], "items": [{"menu_item_id": item["id"], "quantity": 1}]})
            assert r.status_code == 400
            c.put(f"/api/branches/{branch['id']}/menu/{item['id']}", headers=manager, json={"available": True})

            # Money is reported per branch.
            main_before = c.get("/api/reports/daily", headers=main_manager).json()["restaurant"]["revenue"]
            r = c.post(f"/api/orders/{bill['id']}/clear", headers={**cashier, "Idempotency-Key": uuid4().hex},
                       json={"method": "cash", "amount": 500, "expected_version": bill["version"]})
            assert r.status_code == 201, r.text
            assert c.get("/api/reports/daily", headers=main_manager).json()["restaurant"]["revenue"] == main_before
            assert c.get("/api/reports/daily", headers=manager).json()["restaurant"]["revenue"] == 500
            assert c.get("/api/reports/daily", headers=in_branch).json()["restaurant"]["revenue"] == 500

            # Stock and car-wash bays are per branch too, so names and numbers can repeat.
            name = "Rice " + uuid4().hex[:6]
            for headers in (main_manager, manager):
                r = c.post("/api/stock/ingredients", headers=headers, json={"name": name, "unit": "kg", "min_level": 1, "current_stock": 5})
                assert r.status_code == 201, r.text
            main_stock = c.get("/api/stock/ingredients", headers=main_manager).json()
            assert [i["name"] for i in main_stock].count(name) == 1
            bay = 9000 + int(uuid4().int % 900)
            for headers in ({**director, "X-Branch-Id": "1"}, in_branch):
                r = c.post("/api/carwash/bays", headers=headers, json={"bay_number": bay, "name": "Bay " + str(bay)})
                assert r.status_code == 201, r.text
            assert [b["bay_number"] for b in c.get("/api/carwash/bays", headers=in_branch).json()].count(bay) == 1

            # Staff lists are per branch for managers.
            assert {u["branch_id"] for u in c.get("/api/admin/users", headers=manager).json()} == {branch["id"]}
            assert [b["id"] for b in c.get("/api/branches", headers=manager).json()] == [branch["id"]]
            assert len(c.get("/api/branches", headers=director).json()) >= 2
        finally:
            # Leave one active branch so other tests keep working without choosing one.
            r = c.put(f"/api/branches/{branch['id']}", headers=director, json={"is_active": False})
            assert r.status_code == 200, r.text
        # Staff of a closed branch can no longer work in it.
        assert c.get("/api/orders", headers=waiter).status_code == 403


def test_last_active_branch_cannot_be_deactivated():
    with TestClient(app) as c:
        director = login(c)
        active = [b for b in c.get("/api/branches", headers=director).json() if b["is_active"]]
        assert len(active) == 1
        assert c.put(f"/api/branches/{active[0]['id']}", headers=director, json={"is_active": False}).status_code == 400
