"""Exact money storage and Alembic-managed upgrades."""
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.database import SessionLocal, to_money
from app.main import app
from app.migrations import current_revision, head_revision, upgrade
from app.models import Order
from test_integration import login, new_menu, new_table


def test_to_money_rounds_half_up_to_cents():
    assert to_money(0.1 + 0.2) == Decimal("0.30")
    assert to_money("2.675") == Decimal("2.68")
    assert to_money(Decimal("10")) == Decimal("10.00")
    assert to_money(None) is None


def test_totals_are_exact_cents_and_api_returns_numbers():
    with TestClient(app) as c:
        manager = login(c, "manager@gmail.com", "manager123")
        waiter = login(c, "waiter@gmail.com", "waiter123")
        cashier = login(c, "cashier@gmail.com", "cashier123")
        item = new_menu(c, manager, 0.1)
        r = c.post("/api/orders", headers={**waiter, "Idempotency-Key": uuid4().hex},
                   json={"table_id": new_table(c, manager), "items": [{"menu_item_id": item["id"], "quantity": 3}]})
        assert r.status_code == 201, r.text
        bill = r.json()
        # 3 x 0.10 is 0.30 exactly, not 0.30000000000000004.
        assert bill["total"] == 0.3 and isinstance(bill["total"], float)
        with SessionLocal() as db:
            assert db.get(Order, bill["id"]).total == Decimal("0.30")
        r = c.post(f"/api/orders/{bill['id']}/clear", headers={**cashier, "Idempotency-Key": uuid4().hex},
                   json={"method": "cash", "amount": 0.3, "tendered_amount": 1, "expected_version": bill["version"]})
        assert r.status_code == 201, r.text


def test_amounts_with_more_than_two_decimals_are_rejected():
    with TestClient(app) as c:
        manager = login(c, "manager@gmail.com", "manager123")
        category = c.post("/api/admin/categories", headers=manager, json={"name": "Cents " + uuid4().hex[:6]}).json()
        department = c.post("/api/admin/departments", headers=manager, json={"name": "Cents " + uuid4().hex[:6]}).json()
        r = c.post("/api/admin/menu", headers=manager, json={"name": "Odd price", "price": 10.005,
                                                            "category_id": category["id"], "department_id": department["id"]})
        assert r.status_code == 422


def test_fresh_database_is_created_at_newest_revision(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "fresh.db"))
    upgrade(engine)
    upgrade(engine)
    with engine.connect() as db:
        assert current_revision(db) == head_revision()
    assert not list(tmp_path.glob("*.bak"))
    engine.dispose()


def test_legacy_float_amounts_are_rounded_to_cents(tmp_path):
    path = tmp_path / "legacy.db"
    engine = create_engine("sqlite:///" + str(path))
    with engine.begin() as db:
        db.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY, order_number VARCHAR(30), waiter_id INTEGER, customer VARCHAR(120), notes TEXT, total FLOAT, status VARCHAR(30), created_at DATETIME, cleared_at DATETIME)"))
        db.execute(text("INSERT INTO orders VALUES (1,'OLD-1',1,'T1',NULL,21.369999999999997,'pending','2025-01-01',NULL)"))
    upgrade(engine)
    with engine.connect() as db:
        assert current_revision(db) == head_revision()
        assert db.execute(text("SELECT total FROM orders WHERE id=1")).scalar() == 21.37
    assert len(list(tmp_path.glob("*.pre-v6-*.bak"))) == 1
    engine.dispose()


def test_alembic_database_is_backed_up_before_new_revisions(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "managed.db"))
    upgrade(engine)
    with engine.begin() as db:
        db.execute(text("UPDATE alembic_version SET version_num='0001_legacy_v6'"))
        db.execute(text("UPDATE carwash_services SET price=price"))
    upgrade(engine)
    with engine.connect() as db:
        assert current_revision(db) == head_revision()
    assert len(list(tmp_path.glob("*.pre-alembic-0001_legacy_v6-*.bak"))) == 1
    engine.dispose()


def test_ready_reports_schema_revision():
    with TestClient(app) as c:
        body = c.get("/ready").json()
        assert body == {"status": "ready", "schema_revision": head_revision()}


def test_postgresql_float_columns_become_exact_numeric():
    from app.database import engine
    import pytest
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL only: run with TEST_DATABASE_URL set to a PostgreSQL database")
    with TestClient(app):
        pass  # startup brings the shared test database to the newest revision
    with engine.begin() as db:
        db.execute(text("ALTER TABLE orders ALTER COLUMN total TYPE double precision"))
        db.execute(text("INSERT INTO users (id, username, password_hash, role, active, token_version, created_at, updated_at) VALUES (990001, 'float-check', 'x', 'waiter', true, 0, now(), now())"))
        db.execute(text("INSERT INTO orders (id, order_number, waiter_id, total, status, version, created_at, updated_at) VALUES (990001, 'FLOAT-1', 990001, 21.369999999999997, 'cancelled', 1, now(), now())"))
        db.execute(text("UPDATE alembic_version SET version_num='0001_legacy_v6'"))
    upgrade(engine)
    with engine.connect() as db:
        assert current_revision(db) == head_revision()
        kind = db.execute(text("SELECT data_type, numeric_precision, numeric_scale FROM information_schema.columns WHERE table_name='orders' AND column_name='total'")).one()
        assert tuple(kind) == ("numeric", 14, 2)
        assert db.execute(text("SELECT total FROM orders WHERE id=990001")).scalar() == Decimal("21.37")


def test_upgrade_real_v6_database_with_foreign_keys_on(tmp_path):
    """A database made by the app before Alembic, upgraded the way the server does it."""
    import sqlite3
    from pathlib import Path
    from sqlalchemy import event
    path = tmp_path / "v6.db"
    with sqlite3.connect(path) as raw:
        raw.executescript((Path(__file__).parent / "fixtures" / "schema_v6.sql").read_text())
    engine = create_engine("sqlite:///" + str(path))
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    upgrade(engine)
    with engine.connect() as db:
        assert current_revision(db) == head_revision()
        assert db.execute(text("SELECT total, branch_id FROM orders")).one() == (348.3, 1)
        assert db.execute(text("SELECT number, branch_id FROM dining_tables")).one() == (5, 1)
        assert db.execute(text("SELECT count(*) FROM users WHERE role != 'director' AND branch_id IS NULL")).scalar() == 0
        assert db.execute(text("SELECT branch_id FROM users WHERE username='director@gmail.com'")).scalar() is None
        assert db.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert db.execute(text("PRAGMA foreign_key_check")).all() == []
    assert len(list(tmp_path.glob("*.pre-v6-*.bak"))) == 1
    engine.dispose()
