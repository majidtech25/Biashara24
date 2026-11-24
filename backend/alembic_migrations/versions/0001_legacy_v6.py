"""Starting point: the schema as left by the legacy upgrades (schema version 6).

Databases created before Alembic are brought to this point by
app/legacy_migrations.py and then stamped with this revision.

Revision ID: 0001_legacy_v6
Revises:
Create Date: 2026-11-24
"""
from typing import Sequence, Union

revision: str = "0001_legacy_v6"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
