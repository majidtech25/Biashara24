"""Ingredient packs (unit conversion) and stock batches with expiry dates.

Revision ID: 0008_packs_and_batches
Revises: 0007_stock_unit_cost
Create Date: 2026-11-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_packs_and_batches"
down_revision: Union[str, Sequence[str], None] = "0007_stock_unit_cost"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "ingredient_packs" not in tables:
        op.create_table(
            "ingredient_packs",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("ingredient_id", sa.Integer, sa.ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(40), nullable=False),
            sa.Column("factor", sa.Numeric(14, 6), nullable=False),
            sa.Column("created_at", sa.DateTime),
            sa.UniqueConstraint("ingredient_id", "name", name="uq_ingredient_pack_name"),
        )
        op.create_index("ix_ingredient_packs_ingredient_id", "ingredient_packs", ["ingredient_id"])
    if "stock_batches" not in tables:
        op.create_table(
            "stock_batches",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("branch_id", sa.Integer, sa.ForeignKey("branches.id")),
            sa.Column("ingredient_id", sa.Integer, sa.ForeignKey("ingredients.id"), nullable=False),
            sa.Column("document_id", sa.Integer, sa.ForeignKey("stock_documents.id")),
            sa.Column("quantity", sa.Float, nullable=False),
            sa.Column("remaining", sa.Float, nullable=False),
            sa.Column("expiry_date", sa.Date, nullable=False),
            sa.Column("received_at", sa.DateTime),
        )
        op.create_index("ix_stock_batches_branch_id", "stock_batches", ["branch_id"])
        op.create_index("ix_stock_batches_ingredient_id", "stock_batches", ["ingredient_id"])
        op.create_index("ix_stock_batches_expiry_date", "stock_batches", ["expiry_date"])


def downgrade() -> None:
    op.drop_table("stock_batches")
    op.drop_table("ingredient_packs")
