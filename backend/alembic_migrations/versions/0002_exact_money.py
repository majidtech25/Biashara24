"""Store money as exact NUMERIC(14, 2) instead of floating point.

Existing amounts are rounded half-up to whole cents. On PostgreSQL the columns
change type to NUMERIC(14, 2). SQLite has no exact decimal storage and ignores
declared column types, so there only the stored values are rounded; the app
quantizes every amount to cents when reading and writing (app.database.Money).

Revision ID: 0002_exact_money
Revises: 0001_legacy_v6
Create Date: 2026-11-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_exact_money"
down_revision: Union[str, Sequence[str], None] = "0001_legacy_v6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MONEY_COLUMNS = {
    "carwash_services": ("price",),
    "carwash_transactions": ("amount",),
    "cash_shifts": ("opening_float", "counted_cash", "expected_cash"),
    "daily_summaries": ("restaurant_revenue", "restaurant_cash", "restaurant_mpesa",
                        "carwash_revenue", "carwash_cash", "carwash_mpesa"),
    "menu_items": ("price",),
    "order_items": ("price_at_time",),
    "orders": ("total",),
    "payments": ("amount", "tendered_amount", "change_amount"),
    "refunds": ("amount",),
    "till_movements": ("amount",),
}


def _existing_columns():
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    return {table: {c["name"] for c in inspector.get_columns(table)} for table in MONEY_COLUMNS if table in tables}


def upgrade() -> None:
    bind = op.get_bind()
    existing = _existing_columns()
    for table, columns in MONEY_COLUMNS.items():
        for column in columns:
            if column not in existing.get(table, ()):
                continue
            if bind.dialect.name == "postgresql":
                op.alter_column(table, column, type_=sa.Numeric(14, 2),
                                postgresql_using=f'ROUND("{column}"::numeric, 2)')
            else:
                op.execute(sa.text(f'UPDATE "{table}" SET "{column}" = ROUND("{column}", 2) WHERE "{column}" IS NOT NULL'))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # SQLite values stay valid floating-point numbers.
    existing = _existing_columns()
    for table, columns in MONEY_COLUMNS.items():
        for column in columns:
            if column in existing.get(table, ()):
                op.alter_column(table, column, type_=sa.Float(), postgresql_using=f'"{column}"::double precision')
