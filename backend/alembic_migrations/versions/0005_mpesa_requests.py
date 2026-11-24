"""M-Pesa Express prompts.

Adds mpesa_requests: one row per payment prompt sent to a customer's phone, with the
result Safaricom reports back.

Revision ID: 0005_mpesa_requests
Revises: 0004_carwash_lifecycle
Create Date: 2026-11-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_mpesa_requests"
down_revision: Union[str, Sequence[str], None] = "0004_carwash_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "mpesa_requests" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "mpesa_requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("checkout_request_id", sa.String(100), unique=True),
        sa.Column("merchant_request_id", sa.String(100)),
        sa.Column("order_id", sa.Integer, sa.ForeignKey("orders.id"), index=True),
        sa.Column("carwash_id", sa.Integer, sa.ForeignKey("carwash_transactions.id"), index=True),
        sa.Column("phone", sa.String(15), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("result_code", sa.String(20)),
        sa.Column("result_desc", sa.String(300)),
        sa.Column("receipt", sa.String(30), unique=True),
        sa.Column("paid_amount", sa.Numeric(14, 2)),
        sa.Column("paid_phone", sa.String(15)),
        sa.Column("payment_id", sa.Integer, sa.ForeignKey("payments.id")),
        sa.Column("note", sa.String(500)),
        sa.Column("callback", sa.JSON),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, index=True),
        sa.Column("checked_at", sa.DateTime),
        sa.Column("finished_at", sa.DateTime),
        sa.Column("resolved_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("branch_id", sa.Integer, sa.ForeignKey("branches.id"), index=True),
    )


def downgrade() -> None:
    raise NotImplementedError("Restore the pre-upgrade backup instead.")
