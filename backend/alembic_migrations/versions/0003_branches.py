"""Branches: every operational record belongs to a branch.

Creates the branches table with a "Main branch", attaches all existing records and
non-director staff to it, adds per-branch menu availability, and makes table numbers,
bay numbers, ingredient names, daily summaries and recipe versions unique per branch
instead of across the whole business.

Written to be safe on databases whose legacy upgrade already created some of these
columns, which is why every step checks the current schema first.

Revision ID: 0003_branches
Revises: 0002_exact_money
Create Date: 2026-11-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_branches"
down_revision: Union[str, Sequence[str], None] = "0002_exact_money"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCOPED_TABLES = (
    "orders", "payments", "carwash_bays", "carwash_transactions", "ingredients",
    "stock_transactions", "recipes", "stock_reservations", "kitchen_lines", "food_waste",
    "stock_documents", "cash_shifts", "till_movements", "refunds", "daily_summaries",
    "dining_tables", "bill_change_requests",
)

# table: (old unique columns, new constraint name, new unique columns)
PER_BRANCH_UNIQUE = {
    "dining_tables": (["number"], "uq_dining_table_branch_number", ["branch_id", "number"]),
    "carwash_bays": (["bay_number"], "uq_carwash_bay_branch_number", ["branch_id", "bay_number"]),
    "ingredients": (["name"], "uq_ingredient_branch_name", ["branch_id", "name"]),
    "daily_summaries": (["summary_date"], "uq_daily_summary_branch_date", ["branch_id", "summary_date"]),
    "recipes": (["menu_item_id", "version"], "uq_recipe_branch_item_version", ["branch_id", "menu_item_id", "version"]),
}

SQLITE_NAMING = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def _columns(inspector, table):
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "branches" not in tables:
        op.create_table(
            "branches",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("name", sa.String(120), nullable=False, unique=True),
            sa.Column("code", sa.String(20), nullable=False, unique=True),
            sa.Column("address", sa.String(255)),
            sa.Column("phone", sa.String(30)),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        )
    if not bind.execute(sa.text("SELECT id FROM branches WHERE id = 1")).first():
        bind.execute(sa.text("INSERT INTO branches (id, name, code, is_active, created_at) "
                             "VALUES (1, 'Main branch', 'MAIN', :active, CURRENT_TIMESTAMP)"), {"active": True})
        if bind.dialect.name == "postgresql":
            bind.execute(sa.text("SELECT setval(pg_get_serial_sequence('branches', 'id'), (SELECT max(id) FROM branches))"))

    if "branch_menu_items" not in tables:
        op.create_table(
            "branch_menu_items",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("branch_id", sa.Integer, sa.ForeignKey("branches.id"), nullable=False, index=True),
            sa.Column("menu_item_id", sa.Integer, sa.ForeignKey("menu_items.id"), nullable=False, index=True),
            sa.Column("available", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("branch_id", "menu_item_id", name="uq_branch_menu_item"),
        )

    if "branch_id" not in _columns(inspector, "users"):
        with op.batch_alter_table("users") as batch:
            batch.add_column(sa.Column("branch_id", sa.Integer, nullable=True))
            batch.create_foreign_key("fk_users_branch_id", "branches", ["branch_id"], ["id"])
            batch.create_index("ix_users_branch_id", ["branch_id"])
    bind.execute(sa.text("UPDATE users SET branch_id = 1 WHERE branch_id IS NULL AND role != 'director'"))

    for table in SCOPED_TABLES:
        if table not in tables:
            continue
        if "branch_id" not in _columns(inspector, table):
            with op.batch_alter_table(table) as batch:
                batch.add_column(sa.Column("branch_id", sa.Integer, nullable=True))
                batch.create_foreign_key(f"fk_{table}_branch_id", "branches", ["branch_id"], ["id"])
                batch.create_index(f"ix_{table}_branch_id", ["branch_id"])
        bind.execute(sa.text(f'UPDATE "{table}" SET branch_id = 1 WHERE branch_id IS NULL'))

    inspector = sa.inspect(bind)
    for table, (old_columns, new_name, new_columns) in PER_BRANCH_UNIQUE.items():
        if table not in tables:
            continue
        uniques = inspector.get_unique_constraints(table)
        if any(u["name"] == new_name for u in uniques):
            continue
        old = [u for u in uniques if sorted(u["column_names"]) == sorted(old_columns)]
        if bind.dialect.name == "sqlite":
            # SQLite cannot drop constraints in place; batch mode rebuilds the table.
            # The naming convention gives the old unnamed constraint a name to drop.
            with op.batch_alter_table(table, recreate="always", naming_convention=SQLITE_NAMING) as batch:
                if old:
                    batch.drop_constraint(old[0]["name"] or SQLITE_NAMING["uq"] % {
                        "table_name": table, "column_0_name": old_columns[0]}, type_="unique")
                batch.create_unique_constraint(new_name, new_columns)
        else:
            for constraint in old:
                op.drop_constraint(constraint["name"], table, type_="unique")
            op.create_unique_constraint(new_name, table, new_columns)


def downgrade() -> None:
    raise NotImplementedError("Branches cannot be removed automatically; restore the pre-upgrade backup instead.")
