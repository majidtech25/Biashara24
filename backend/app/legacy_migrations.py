"""Frozen pre-Alembic upgrades (schema versions 1-6) for databases created before Alembic.

Do not add new changes here. New schema changes are Alembic revisions in
backend/alembic_migrations/versions. This module only brings an older database up to
schema version 6, after which Alembic takes over (see app/migrations.py).
"""
from datetime import datetime
from pathlib import Path
import sqlite3
from contextlib import closing
from sqlalchemy import inspect, text
from .database import Base

VERSION = 6

# Tables and columns as they existed at schema version 6. The legacy upgrade only
# creates or adds these, so later Alembic revisions never collide with it.
LEGACY_V6_COLUMNS = {
    'business_settings': ('id', 'values', 'version'),
    'carwash_bays': ('bay_number', 'created_at', 'id', 'is_active', 'name'),
    'carwash_services': ('created_at', 'description', 'duration_minutes', 'id', 'is_active', 'name', 'price'),
    'categories': ('created_at', 'description', 'id', 'is_active', 'name'),
    'daily_summaries': ('carwash_cash', 'carwash_count', 'carwash_mpesa', 'carwash_revenue', 'created_at', 'id', 'low_stock_items', 'restaurant_cash', 'restaurant_mpesa', 'restaurant_orders_count', 'restaurant_revenue', 'summary_date', 'updated_at'),
    'departments': ('created_at', 'id', 'is_active', 'name', 'printer_ip', 'printer_port'),
    'dining_tables': ('id', 'is_active', 'number'),
    'external_receipts': ('created_at', 'reference', 'source', 'source_id'),
    'ingredients': ('cost_per_unit', 'created_at', 'current_stock', 'description', 'id', 'is_active', 'last_updated', 'min_level', 'name', 'reorder_quantity', 'unit'),
    'menu_images': ('content', 'content_type', 'id'),
    'revoked_tokens': ('expires_at', 'id', 'jti'),
    'suppliers': ('active', 'contact', 'id', 'name'),
    'menu_items': ('active', 'category_id', 'created_at', 'department_id', 'description', 'id', 'image_url', 'name', 'price', 'tax_rate', 'updated_at'),
    'users': ('active', 'created_at', 'department_id', 'email', 'full_name', 'id', 'password_hash', 'phone', 'role', 'token_version', 'updated_at', 'username'),
    'audit_logs': ('action', 'entity_id', 'entity_type', 'id', 'ip_address', 'module', 'new_values', 'old_values', 'timestamp', 'user_id'),
    'cash_shifts': ('active_cashier_id', 'cashier_id', 'closed_at', 'counted_cash', 'expected_cash', 'id', 'opened_at', 'opening_float', 'reviewed_at', 'reviewed_by', 'status', 'variance_reason'),
    'orders': ('cleared_at', 'created_at', 'customer', 'id', 'notes', 'order_number', 'status', 'table_id', 'total', 'updated_at', 'version', 'waiter_id'),
    'recipes': ('components', 'created_at', 'created_by', 'id', 'menu_item_id', 'version'),
    'stock_documents': ('created_at', 'created_by', 'id', 'kind', 'lines', 'posted_at', 'posted_by', 'reason', 'reference', 'status', 'supplier_id'),
    'stock_transactions': ('id', 'ingredient_id', 'performed_by', 'quantity', 'quantity_after', 'quantity_before', 'reason', 'reference_id', 'reference_type', 'timestamp', 'transaction_type'),
    'write_submissions': ('created_at', 'fingerprint', 'id', 'key', 'response', 'user_id'),
    'bill_change_requests': ('created_at', 'decided_at', 'decided_by', 'decision_reason', 'id', 'items', 'kind', 'order_id', 'reason', 'requested_by', 'status'),
    'carwash_transactions': ('amount', 'bay_id', 'completed_at', 'created_at', 'created_by', 'id', 'mpesa_reference', 'notes', 'payment_method', 'payment_status', 'service_id', 'service_name_at_time', 'shift_id', 'started_at', 'transaction_number', 'vehicle_plate', 'vehicle_type'),
    'notifications': ('created_at', 'id', 'message', 'order_id', 'read_at', 'user_id'),
    'order_batches': ('created_at', 'created_by', 'deliveries', 'id', 'items', 'kind', 'notes', 'order_id'),
    'order_items': ('created_at', 'department_id_at_time', 'department_name_at_time', 'id', 'menu_item_id', 'name_at_time', 'order_id', 'price_at_time', 'quantity', 'ready', 'tax_rate_at_time', 'voided_quantity'),
    'order_status_history': ('changed_at', 'changed_by', 'id', 'order_id', 'status'),
    'payments': ('active_order_id', 'amount', 'change_amount', 'completed_at', 'created_at', 'id', 'method', 'notes', 'order_id', 'receipt_snapshot', 'recorded_by', 'reference', 'rejected_at', 'rejected_by', 'rejection_reason', 'shift_id', 'status', 'tendered_amount', 'verified_by'),
    'table_reservations': ('order_id', 'table_id'),
    'till_movements': ('amount', 'created_at', 'id', 'reason', 'recorded_by', 'shift_id'),
    'bill_submissions': ('batch_id', 'fingerprint', 'id', 'key', 'order_id', 'user_id'),
    'food_waste': ('created_at', 'id', 'ingredients', 'order_item_id', 'quantity', 'reason', 'recorded_by'),
    'kitchen_lines': ('order_item_id', 'ready_at', 'recipe_snapshot', 'served_at', 'started_at', 'status', 'version'),
    'refunds': ('amount', 'created_at', 'id', 'payment_id', 'reason', 'recorded_by', 'reference', 'shift_id'),
    'stock_reservations': ('ingredient_id', 'order_item_id', 'quantity'),
}

# Defaults for existing rows when adding the fields introduced by this migration.
DEFAULTS = {"updated_at": "CURRENT_TIMESTAMP", "created_at": "CURRENT_TIMESTAMP",
            "started_at": "CURRENT_TIMESTAMP", "is_active": "1", "printer_port": "9100",
            "reorder_quantity": "0", "cost_per_unit": "0", "version": "1", "voided_quantity": "0", "tax_rate": "16"}

def legacy_upgrade(engine, backup=True):
    from . import models
    existing = inspect(engine).get_table_names()
    v6_tables = [t for t in Base.metadata.sorted_tables if t.name in LEGACY_V6_COLUMNS]
    missing = [(table, col) for table in v6_tables if table.name in existing
               for col in table.columns if col.name in LEGACY_V6_COLUMNS[table.name]
               and col.name not in {c["name"] for c in inspect(engine).get_columns(table.name)}]
    old_payment_unique = 'payments' in existing and any(c['column_names'] == ['order_id'] for c in inspect(engine).get_unique_constraints('payments'))
    if (missing or old_payment_unique) and engine.dialect.name != "sqlite":
        raise RuntimeError("An existing non-SQLite database needs a reviewed schema migration before startup.")
    pending_version = bool(existing) and "schema_versions" not in existing
    if existing and "schema_versions" in existing:
        with engine.connect() as conn:
            pending_version = not conn.execute(text("SELECT version FROM schema_versions WHERE version = :version"), {"version":VERSION}).first()
    if backup and (missing or pending_version or old_payment_unique) and engine.url.database and engine.url.database != ":memory:" and engine.dialect.name == "sqlite":
        source = Path(engine.url.database).resolve()
        backup = source.with_name(source.name + f".pre-v{VERSION}-" + datetime.now().strftime("%Y%m%d%H%M%S%f") + ".bak")
        with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(backup)) as dst:
            src.backup(dst)
    Base.metadata.create_all(engine, tables=v6_tables)
    with engine.begin() as conn:
        for table, col in missing:
            # SQLite cannot add CURRENT_TIMESTAMP defaults. Backfill explicitly.
            kind = col.type.compile(dialect=engine.dialect)
            fk = next(iter(col.foreign_keys), None)
            reference = f' REFERENCES "{fk.column.table.name}"("{fk.column.name}")' if fk else ""
            conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {kind}{reference}'))
            default = DEFAULTS.get(col.name)
            if default:
                conn.execute(text(f'UPDATE "{table.name}" SET "{col.name}" = {default} WHERE "{col.name}" IS NULL'))
        if "carwash_transactions" in existing:
            conn.execute(text("UPDATE carwash_transactions SET transaction_number = 'CW-LEGACY-' || id WHERE transaction_number IS NULL"))
        if old_payment_unique:
            # SQLite cannot drop an inline UNIQUE constraint. Copy all columns and
            # IDs into the new schema inside this transaction, with a pre-upgrade backup.
            from sqlalchemy.schema import CreateTable
            from .models import Payment
            table = Payment.__table__
            ddl = str(CreateTable(table).compile(dialect=engine.dialect))
            conn.execute(text(ddl.replace('CREATE TABLE payments', 'CREATE TABLE payments_upgrade', 1)))
            columns = ', '.join('"' + c.name + '"' for c in table.columns)
            conn.execute(text(f'INSERT INTO payments_upgrade ({columns}) SELECT {columns} FROM payments'))
            conn.execute(text('DROP TABLE payments'))
            conn.execute(text('ALTER TABLE payments_upgrade RENAME TO payments'))
        for table in v6_tables:
            for idx in table.indexes:
                # Only indexes on version-6 columns; later ones belong to Alembic revisions.
                if all(c.name in LEGACY_V6_COLUMNS[table.name] for c in idx.columns):
                    idx.create(conn, checkfirst=True)
        if engine.dialect.name == "sqlite":
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_wash_number ON carwash_transactions(transaction_number)"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS schema_versions (version INTEGER PRIMARY KEY)"))
        if not conn.execute(text("SELECT version FROM schema_versions WHERE version = 1")).first():
            conn.execute(text("INSERT INTO schema_versions(version) VALUES (1)"))
        if not conn.execute(text("SELECT version FROM schema_versions WHERE version = 2")).first():
            conn.execute(text("INSERT INTO schema_versions(version) VALUES (2)"))
        if not conn.execute(text("SELECT version FROM schema_versions WHERE version = 3")).first():
            conn.execute(text("INSERT INTO schema_versions(version) VALUES (3)"))
        if not conn.execute(text("SELECT version FROM schema_versions WHERE version = 4")).first():
            # Recover only recorded submission history, never today's edited menu.
            import json
            for items, deliveries in conn.execute(text("SELECT items, deliveries FROM order_batches WHERE kind IN ('original','addition') ORDER BY id")):
                items = json.loads(items) if isinstance(items, str) else items
                deliveries = json.loads(deliveries) if isinstance(deliveries, str) else deliveries
                names = {d['department_id']: d.get('department') for d in deliveries or []}
                for item in items or []:
                    conn.execute(text("UPDATE order_items SET name_at_time=:name, department_id_at_time=:department, department_name_at_time=:department_name WHERE id=:id AND name_at_time IS NULL"),
                                 {"id":item['order_item_id'], "name":item['name'], "department":item['department_id'],
                                  "department_name":item.get('department_name') or names.get(item['department_id'])})
            conn.execute(text("INSERT INTO schema_versions(version) VALUES (4)"))
        if not conn.execute(text("SELECT version FROM schema_versions WHERE version = 5")).first():
            conn.execute(text("UPDATE payments SET active_order_id=order_id WHERE status != 'rejected'"))
            conn.execute(text("INSERT INTO schema_versions(version) VALUES (5)"))
        if not conn.execute(text("SELECT version FROM schema_versions WHERE version = 6")).first():
            # Keep existing open food visible without inventing historical recipes
            # or deducting ingredients that might already have been consumed.
            conn.execute(text("""INSERT INTO kitchen_lines (order_item_id,status,version,recipe_snapshot)
                SELECT i.id, CASE WHEN i.ready THEN 'ready' ELSE 'pending' END, 1, '[]'
                FROM order_items i JOIN orders o ON o.id=i.order_id
                WHERE o.status NOT IN ('cleared','completed','cancelled')
                  AND i.quantity > i.voided_quantity
                  AND NOT EXISTS (SELECT 1 FROM kitchen_lines k WHERE k.order_item_id=i.id)"""))
            conn.execute(text("INSERT INTO schema_versions(version) VALUES (6)"))
