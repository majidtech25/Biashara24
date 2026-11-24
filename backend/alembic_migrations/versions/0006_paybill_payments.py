"""Paybill payments reported by Safaricom, replacing phone prompts.

Drops mpesa_requests (phone prompts, which the business decided not to use) and adds
c2b_payments: one row per payment into the business Paybill.

Revision ID: 0006_paybill_payments
Revises: 0005_mpesa_requests
Create Date: 2026-11-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_paybill_payments"
down_revision: Union[str, Sequence[str], None] = "0005_mpesa_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "mpesa_requests" in tables:
        op.drop_table("mpesa_requests")
    if "c2b_payments" in tables:
        return
    op.create_table(
        "c2b_payments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("trans_id", sa.String(30), nullable=False, unique=True),
        sa.Column("trans_type", sa.String(30)),
        sa.Column("trans_time", sa.String(14)),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("account", sa.String(40), index=True),
        sa.Column("msisdn", sa.String(30)),
        sa.Column("payer_name", sa.String(120)),
        sa.Column("branch_id", sa.Integer, sa.ForeignKey("branches.id"), index=True),
        sa.Column("order_id", sa.Integer, sa.ForeignKey("orders.id"), index=True),
        sa.Column("carwash_id", sa.Integer, sa.ForeignKey("carwash_transactions.id"), index=True),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("payment_id", sa.Integer, sa.ForeignKey("payments.id")),
        sa.Column("used_at", sa.DateTime),
        sa.Column("raw", sa.JSON),
        sa.Column("received_at", sa.DateTime, nullable=False, index=True),
    )


def downgrade() -> None:
    raise NotImplementedError("Restore the pre-upgrade backup instead.")
