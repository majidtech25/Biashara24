"""Failed sign-in limits and default-account protection in production."""
from uuid import uuid4

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.middleware.auth import hash_password
from app.models import User
from app.services import login_limiter
from app.services.seed_accounts import disable_default_accounts


def test_repeated_failed_sign_ins_are_locked_out():
    with TestClient(app) as c:
        bad = {"username": "manager@gmail.com", "password": "not-the-password"}
        for _ in range(login_limiter.MAX_FAILURES):
            assert c.post("/auth/login", json=bad).status_code == 401
        blocked = c.post("/auth/login", json={"username": "manager@gmail.com", "password": "manager123"})
        assert blocked.status_code == 429
        assert int(blocked.headers["Retry-After"]) > 0
        # Other accounts are unaffected.
        assert c.post("/auth/login", json={"username": "cashier@gmail.com", "password": "cashier123"}).status_code == 200


def test_successful_sign_in_clears_failures():
    with TestClient(app) as c:
        bad = {"username": "waiter@gmail.com", "password": "nope"}
        for _ in range(login_limiter.MAX_FAILURES - 1):
            assert c.post("/auth/login", json=bad).status_code == 401
        assert c.post("/auth/login", json={"username": "waiter@gmail.com", "password": "waiter123"}).status_code == 200
        for _ in range(login_limiter.MAX_FAILURES - 1):
            assert c.post("/auth/login", json=bad).status_code == 401
        assert c.post("/auth/login", json={"username": "waiter@gmail.com", "password": "waiter123"}).status_code == 200


def test_default_passwords_are_disabled_but_changed_ones_are_kept():
    with TestClient(app):
        pass  # development startup seeds the initial accounts
    with SessionLocal() as db:
        manager = db.query(User).filter_by(username="manager@gmail.com").one()
        original_hash = manager.password_hash
        manager.password_hash = hash_password("a-new-strong-password-" + uuid4().hex)
        db.flush()
        disabled = disable_default_accounts(db)
        assert "director@gmail.com" in disabled and "manager@gmail.com" not in disabled
        assert db.query(User).filter_by(username="director@gmail.com").one().active is False
        assert db.query(User).filter_by(username="manager@gmail.com").one().active is True
        db.rollback()  # leave the shared test accounts unchanged
        assert db.query(User).filter_by(username="manager@gmail.com").one().password_hash == original_hash
