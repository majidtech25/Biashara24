"""Printers per branch.

Revision ID: 0010_branch_printers
Revises: 0009_takeaway_and_split
Create Date: 2026-11-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_branch_printers"
down_revision: Union[str, Sequence[str], None] = "0009_takeaway_and_split"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "branch_printers" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "branch_printers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("branch_id", sa.Integer, sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("department_id", sa.Integer, sa.ForeignKey("departments.id"), nullable=False),
        sa.Column("printer_ip", sa.String(80), nullable=False),
        sa.Column("printer_port", sa.Integer, nullable=False, server_default="9100"),
        sa.Column("created_at", sa.DateTime),
        sa.UniqueConstraint("branch_id", "department_id", name="uq_branch_printer"),
    )
    op.create_index("ix_branch_printers_branch_id", "branch_printers", ["branch_id"])
    op.create_index("ix_branch_printers_department_id", "branch_printers", ["department_id"])


def downgrade() -> None:
    op.drop_table("branch_printers")
