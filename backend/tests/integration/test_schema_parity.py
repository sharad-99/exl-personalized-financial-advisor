"""The SQL migrations (PostgreSQL source of truth) and the ORM models must agree
on tables and columns. Runs without a database by parsing the SQL."""

import re
from pathlib import Path

from app.models.tables import ALL_TABLES, Base

MIGRATION = Path(__file__).resolve().parents[3] / "supabase" / "migrations" / "20261024000100_initial_schema.sql"
TABLE_RE = re.compile(r"create table if not exists public\.(\w+) \((.*?)\n\);", re.S)
COLUMN_RE = re.compile(r"^([a-z_]+)\s+(uuid|text|boolean|timestamptz|numeric|date|char|smallint|integer|jsonb)\b")


def sql_columns() -> dict[str, set[str]]:
    tables: dict[str, set[str]] = {}
    for name, body in TABLE_RE.findall(MIGRATION.read_text(encoding="utf-8")):
        cols = {m.group(1) for line in body.splitlines() if (m := COLUMN_RE.match(line.strip()))}
        tables[name] = cols
    return tables


def test_tables_match() -> None:
    assert set(sql_columns()) == set(ALL_TABLES) == set(Base.metadata.tables)


def test_columns_match() -> None:
    sql = sql_columns()
    for name, table in Base.metadata.tables.items():
        assert {c.name for c in table.columns} == sql[name], name
