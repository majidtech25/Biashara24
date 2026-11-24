"""Record the ingredient cost on each stock movement, for profit reports.

Revision ID: 0007_stock_unit_cost
Revises: 0006_paybill_payments
Create Date: 2026-11-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_stock_unit_cost"
down_revision: Union[str, Sequence[str], None] = "0006_paybill_payments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("stock_transactions")}
    if "unit_cost" not in existing:
        with op.batch_alter_table("stock_transactions") as batch:
            batch.add_column(sa.Column("unit_cost", sa.Numeric(14, 4), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("stock_transactions") as batch:
        batch.drop_column("unit_cost")
