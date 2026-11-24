import json
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import Numeric, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.types import TypeDecorator
from .config import get_settings

CENT = Decimal("0.01")


def to_money(value):
    """Convert a number to an exact shilling amount with cents (half-up rounding)."""
    if value is None:
        return None
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


class Money(TypeDecorator):
    """Exact currency amount stored as NUMERIC(14, 2) and returned as Decimal.

    PostgreSQL stores NUMERIC exactly. SQLite has no exact decimal storage, so the
    value is quantized to cents on every write and read; amounts below 10^12 round-trip
    exactly at two decimal places.
    """
    impl = Numeric(14, 2, asdecimal=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return to_money(value)

    def process_result_value(self, value, dialect):
        return to_money(value)


def _json_default(value):
    # JSON snapshots keep numbers as numbers for existing readers.
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def json_dumps(value):
    return json.dumps(value, default=_json_default)

settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True, json_serializer=json_dumps)

if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
