"""Database upgrades, run at startup.

New schema changes are Alembic revisions in backend/alembic_migrations/versions.
Create one with (from backend/):  alembic revision -m "describe the change"

How a database is brought up to date:
- Empty database: create every table from the models and mark it as current (head).
- Database from before Alembic (schema versions 1-6): run the frozen legacy upgrade
  to version 6, mark it as revision LEGACY_REVISION, then apply newer revisions.
- Database already managed by Alembic: apply any newer revisions.

SQLite files get a backup next to the database before any change.
"""
from contextlib import closing
from datetime import datetime
from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from .database import Base
from .legacy_migrations import VERSION as LEGACY_VERSION, legacy_upgrade

SCRIPT_LOCATION = Path(__file__).resolve().parent.parent / "alembic_migrations"
LEGACY_REVISION = "0001_legacy_v6"


def alembic_config(connection=None):
    config = Config()
    config.set_main_option("script_location", str(SCRIPT_LOCATION))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def head_revision():
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def current_revision(connection):
    return MigrationContext.configure(connection).get_current_revision()


def _backup_sqlite(engine, label):
    if engine.dialect.name != "sqlite" or not engine.url.database or engine.url.database == ":memory:":
        return
    source = Path(engine.url.database).resolve()
    if not source.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    backup = source.with_name(f"{source.name}.pre-{label}-{stamp}.bak")
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(backup)) as dst:
        src.backup(dst)


def upgrade(engine):
    from . import models  # noqa: F401  (registers every table on Base.metadata)

    tables = set(inspect(engine).get_table_names())
    head = head_revision()
    if not tables:
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            command.stamp(alembic_config(connection), "head")
        return
    if "alembic_version" not in tables:
        # One backup covers both the legacy steps and the Alembic revisions after them.
        _backup_sqlite(engine, f"v{LEGACY_VERSION}")
        legacy_upgrade(engine, backup=False)
        with engine.begin() as connection:
            command.stamp(alembic_config(connection), LEGACY_REVISION)
        with engine.begin() as connection:
            command.upgrade(alembic_config(connection), "head")
        return
    with engine.connect() as connection:
        current = current_revision(connection)
    if current == head:
        return
    _backup_sqlite(engine, f"alembic-{current}")
    with engine.begin() as connection:
        command.upgrade(alembic_config(connection), "head")
