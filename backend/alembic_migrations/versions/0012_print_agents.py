"""Print programs at branches.

Revision ID: 0012_print_agents
Revises: 0011_menu_image_dates
Create Date: 2026-11-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_print_agents"
down_revision: Union[str, Sequence[str], None] = "0011_menu_image_dates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "print_agents" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "print_agents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("branch_id", sa.Integer, sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_seen", sa.DateTime),
        sa.Column("created_at", sa.DateTime),
    )
    op.create_index("ix_print_agents_branch_id", "print_agents", ["branch_id"])


def downgrade() -> None:
    op.drop_table("print_agents")
