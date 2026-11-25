import os
import tempfile
from pathlib import Path

# All tests share a fresh temporary database, never the business database.
TEST_DIRECTORY = tempfile.TemporaryDirectory(prefix="biashara360-tests-")
# Set TEST_DATABASE_URL to run the suite on another database, e.g. a disposable
# PostgreSQL database: postgresql+psycopg://user:pass@host/biashara_test
# Every table in that database is dropped first.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
os.environ["DATABASE_URL"] = TEST_DATABASE_URL or "sqlite:///" + str(Path(TEST_DIRECTORY.name) / "test.db")
if TEST_DATABASE_URL and TEST_DATABASE_URL.startswith("postgresql"):
    from sqlalchemy import create_engine, text
    _engine = create_engine(TEST_DATABASE_URL)
    with _engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    _engine.dispose()
os.environ["ENVIRONMENT"] = "development"
os.environ["PRINT_RETRY_SECONDS"] = "0"  # tests call the retry directly

def pytest_sessionfinish(session, exitstatus):
    from app.database import engine
    engine.dispose()
    TEST_DIRECTORY.cleanup()

import pytest


@pytest.fixture(autouse=True)
def _reset_login_limiter():
    from app.services import login_limiter
    login_limiter.reset()
    yield
    login_limiter.reset()


def waiter_headers(client, email="waiter@gmail.com", password="waiter123"):
    """Only waiters send orders to the kitchen, so tests post orders as the seeded waiter."""
    r = client.post("/auth/login", json={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
