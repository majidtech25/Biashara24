"""Takeaway orders and bills split from another bill.

Revision ID: 0009_takeaway_and_split
Revises: 0008_packs_and_batches
Create Date: 2026-11-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_takeaway_and_split"
down_revision: Union[str, Sequence[str], None] = "0008_packs_and_batches"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("orders")}
    with op.batch_alter_table("orders") as batch:
        if "order_type" not in existing:
            batch.add_column(sa.Column("order_type", sa.String(20), nullable=False, server_default="dine_in"))
        if "split_from_id" not in existing:
            batch.add_column(sa.Column("split_from_id", sa.Integer, sa.ForeignKey("orders.id", name="fk_orders_split_from_id")))


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.drop_column("split_from_id")
        batch.drop_column("order_type")
