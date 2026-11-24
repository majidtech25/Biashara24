"""Car-wash attendants and a wash lifecycle separate from payment.

Adds carwash_attendants, and wash_status / attendant / start and finish times on
car-wash transactions. Washes recorded before this upgrade are marked done so that
no bay looks occupied by old records.

Revision ID: 0004_carwash_lifecycle
Revises: 0003_branches
Create Date: 2026-11-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_carwash_lifecycle"
down_revision: Union[str, Sequence[str], None] = "0003_branches"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_COLUMNS = (
    ("wash_status", lambda: sa.Column("wash_status", sa.String(20), nullable=True)),
    ("attendant_id", lambda: sa.Column("attendant_id", sa.Integer, nullable=True)),
    ("wash_started_at", lambda: sa.Column("wash_started_at", sa.DateTime, nullable=True)),
    ("wash_finished_at", lambda: sa.Column("wash_finished_at", sa.DateTime, nullable=True)),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "carwash_attendants" not in tables:
        op.create_table(
            "carwash_attendants",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("phone", sa.String(30)),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column("branch_id", sa.Integer, sa.ForeignKey("branches.id"), nullable=True, index=True),
        )
    if "carwash_transactions" not in tables:
        return
    existing = {c["name"] for c in inspector.get_columns("carwash_transactions")}
    missing = [make() for name, make in NEW_COLUMNS if name not in existing]
    if missing:
        with op.batch_alter_table("carwash_transactions") as batch:
            for column in missing:
                batch.add_column(column)
            if "attendant_id" not in existing:
                batch.create_foreign_key("fk_carwash_transactions_attendant_id", "carwash_attendants", ["attendant_id"], ["id"])
                batch.create_index("ix_carwash_transactions_attendant_id", ["attendant_id"])
            if "wash_status" not in existing:
                batch.create_index("ix_carwash_transactions_wash_status", ["wash_status"])
    bind.execute(sa.text("UPDATE carwash_transactions SET wash_status = 'done', "
                         "wash_finished_at = COALESCE(completed_at, created_at) WHERE wash_status IS NULL"))


def downgrade() -> None:
    raise NotImplementedError("Restore the pre-upgrade backup instead.")
