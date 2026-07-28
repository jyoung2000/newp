"""The Alembic migration chain must build the exact schema the models declare."""
from __future__ import annotations

import os
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command
from app.models import Base

BACKEND = Path(__file__).resolve().parents[1]


def test_upgrade_head_matches_metadata(tmp_path):
    db_path = tmp_path / "migration.db"
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    old_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    try:
        command.upgrade(cfg, "head")
    finally:
        if old_url is not None:
            os.environ["DATABASE_URL"] = old_url

    migrated = create_engine(f"sqlite:///{db_path}")
    migrated_tables = set(inspect(migrated).get_table_names()) - {"alembic_version"}
    model_tables = set(Base.metadata.tables.keys())
    assert migrated_tables == model_tables

    # Column parity per table.
    insp = inspect(migrated)
    for table in sorted(model_tables):
        migrated_cols = {c["name"] for c in insp.get_columns(table)}
        model_cols = {c.name for c in Base.metadata.tables[table].columns}
        assert migrated_cols == model_cols, f"column mismatch in {table}"
    migrated.dispose()
