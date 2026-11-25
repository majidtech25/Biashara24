from fastapi.testclient import TestClient
from app.main import app

def auth(client):
    r=client.post("/auth/login",json={"username":"director@gmail.com","password":"director123"});assert r.status_code==200,r.text
    return {"Authorization":f"Bearer {r.json()['access_token']}"}

def test_health_and_full_sale_flow():
    with TestClient(app) as c:
        assert c.get("/health").status_code==200
        h=auth(c)
        cats=c.post("/api/admin/categories",json={"name":"Test Food"},headers=h);assert cats.status_code in (201,409)
        deps=c.post("/api/admin/departments",json={"name":"Test Kitchen"},headers=h);assert deps.status_code in (201,409)
        categories=c.post("/api/admin/categories",json={"name":"Meals Unique"},headers=h).json()
        department=c.post("/api/admin/departments",json={"name":"Grill Unique"},headers=h).json()
        menu=c.post("/api/admin/menu",json={"name":"Pilau Test","price":350,"category_id":categories["id"],"department_id":department["id"]},headers=h);assert menu.status_code==201,menu.text
        table=c.post("/api/tables",json={"number":9999},headers=h).json()
        h={**h,"Idempotency-Key":"full-sale-flow-test"}
        from conftest import waiter_headers
        order=c.post("/api/orders",json={"table_id":table["id"],"customer":"Amina","items":[{"menu_item_id":menu.json()["id"],"quantity":2}]},headers={**waiter_headers(c),"Idempotency-Key":"full-sale-flow-test"});assert order.status_code==201,order.text;assert order.json()["total"]==700
        paid=c.post(f"/api/orders/{order.json()['id']}/clear",json={"expected_version":order.json()["version"],"method":"m-pesa","amount":700,"reference":"TEST123"},headers=h);assert paid.status_code==201,paid.text
        assert c.get("/api/dashboard",headers=h).status_code==200

def test_rbac_blocks_unauthorized_user_creation():
    with TestClient(app) as c:
        h=auth(c)
        c.post("/api/admin/users",json={"username":"waiter_test","password":"Password123","role":"waiter"},headers=h)
        login=c.post("/auth/login",json={"username":"waiter_test","password":"Password123"}).json()
        waiter={"Authorization":f"Bearer {login['access_token']}"}
        assert c.post("/api/admin/users",json={"username":"bad","password":"Password123","role":"manager"},headers=waiter).status_code==403


def test_workspace_roles_and_server_authorization():
    with TestClient(app) as c:
        director = auth(c)
        for role, allowed, denied in [
            ("store_manager", "/api/stock/history", "/api/carwash/history"),
            ("carwash_manager", "/api/carwash/history", "/api/stock/history"),
            ("cashier", "/api/payments", "/api/stock/history"),
            ("manager", "/api/admin/users", "/api/dashboard"),
        ]:
            username = f"auth_{role}"
            created = c.post("/api/admin/users", json={"username": username, "password": "Password123!", "role": role}, headers=director)
            assert created.status_code == 201, created.text
            login = c.post("/auth/login", json={"username": username, "password": "Password123!"})
            assert login.status_code == 200, login.text
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            assert c.get("/auth/me", headers=headers).json()["role"] == role
            assert c.get(allowed, headers=headers).status_code == 200
            assert c.get(denied, headers=headers).status_code == 403
            if role in {"store_manager", "carwash_manager"}:
                assert c.get("/api/orders", headers=headers).status_code == 403
                assert c.put("/api/orders/1", json={"status": "ready"}, headers=headers).status_code == 403
            assert c.post("/api/admin/users", json={"username": f"forged_{role}", "password": "Password123!", "role": "director"}, headers=headers).status_code == 403


def test_authentication_failures_and_logout_revokes_refresh():
    with TestClient(app) as c:
        assert c.get("/auth/me").status_code == 401
        assert c.post("/auth/login", json={"username": "director@gmail.com", "password": "wrong"}).status_code == 401
        login = c.post("/auth/login", json={"username": "director@gmail.com", "password": "director123"}).json()
        headers = {"Authorization": f"Bearer {login['access_token']}"}
        assert c.post("/auth/logout", headers=headers).status_code == 200
        assert c.get("/auth/me", headers=headers).status_code == 401
        assert c.post("/auth/refresh", json={"refresh_token": login["refresh_token"]}).status_code == 401


def test_role_changes_revoke_old_sessions_and_managers_cannot_promote_themselves():
    with TestClient(app) as c:
        director = auth(c)
        created = c.post("/api/admin/users", json={"username": "role_change_test", "password": "Password123!", "role": "manager"}, headers=director)
        assert created.status_code == 201, created.text
        account_id = created.json()["id"]
        login = c.post("/auth/login", json={"username": "role_change_test", "password": "Password123!"}).json()
        manager = {"Authorization": f"Bearer {login['access_token']}"}
        assert c.put(f"/api/admin/users/{account_id}", json={"role": "director"}, headers=manager).status_code == 403
        assert c.put(f"/api/admin/users/{account_id}", json={"role": "store_manager"}, headers=director).status_code == 200
        assert c.get("/auth/me", headers=manager).status_code == 401
        assert c.post("/auth/refresh", json={"refresh_token": login["refresh_token"]}).status_code == 401
        assert c.put(f"/api/admin/users/{account_id}", json={"active": False}, headers=director).status_code == 200
        assert c.post("/auth/login", json={"username": "role_change_test", "password": "Password123!"}).status_code == 401


def test_initial_company_accounts_and_selected_designation():
    from app.services.seed_accounts import INITIAL_ACCOUNTS
    with TestClient(app) as c:
        for role, email, password, _ in INITIAL_ACCOUNTS:
            result = c.post("/auth/login", json={"username": email, "password": password, "role": role})
            assert result.status_code == 200, result.text
            assert result.json()["user"]["role"] == role
            assert result.json()["user"]["username"] == email
            assert "password" not in result.json()["user"]
            wrong_role = "cashier" if role == "director" else "director"
            mismatch = c.post("/auth/login", json={"username": email, "password": password, "role": wrong_role})
            assert mismatch.status_code == 403, mismatch.text
            assert "access_token" not in mismatch.json()
            assert c.post("/auth/login", json={"username": email, "password": "wrong", "role": role}).status_code == 401
        assert c.post("/auth/login", json={"username": " DIRECTOR@GMAIL.COM ", "password": "director123", "role": "director"}).status_code == 200


def test_seeding_preserves_existing_account_passwords():
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.main import seed
    from app.middleware.auth import hash_password, verify_password
    from app.models import User
    with TestClient(app):
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.username == "store@gmail.com"))
            original_hash = user.password_hash
            original_id = user.id
            user.password_hash = hash_password("UpdatedStore123!")
            db.commit()
        try:
            seed()
            with SessionLocal() as db:
                users = db.scalars(select(User).where(User.username == "store@gmail.com")).all()
                assert len(users) == 1
                assert users[0].id == original_id
                assert verify_password("UpdatedStore123!", users[0].password_hash)
        finally:
            with SessionLocal() as db:
                db.get(User, original_id).password_hash = original_hash
                db.commit()
