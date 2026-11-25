"""Upload time on menu photos, so unused ones can be cleaned up safely.

Revision ID: 0011_menu_image_dates
Revises: 0010_branch_printers
Create Date: 2026-11-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011_menu_image_dates"
down_revision: Union[str, Sequence[str], None] = "0010_branch_printers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "created_at" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("menu_images")}:
        with op.batch_alter_table("menu_images") as batch:
            batch.add_column(sa.Column("created_at", sa.DateTime))


def downgrade() -> None:
    with op.batch_alter_table("menu_images") as batch:
        batch.drop_column("created_at")
