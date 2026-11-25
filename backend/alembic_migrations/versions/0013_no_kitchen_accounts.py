"""Remove kitchen accounts: the business does not use a kitchen screen (Majid, 2026-11-25).

Existing kitchen accounts are switched off, not deleted, so their history in the audit log stays readable.

Revision ID: 0013_no_kitchen_accounts
Revises: 0012_print_agents
Create Date: 2026-11-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013_no_kitchen_accounts"
down_revision: Union[str, Sequence[str], None] = "0012_print_agents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    users = sa.table("users", sa.column("role", sa.String), sa.column("active", sa.Boolean),
                     sa.column("token_version", sa.Integer))
    # Switch the accounts off and end any session they still have.
    op.execute(users.update().where(users.c.role == "kitchen")
               .values(active=False, token_version=users.c.token_version + 1))


def downgrade() -> None:
    pass  # the accounts stay switched off
