"""Apply the SQL migrations in supabase/migrations to a PostgreSQL database.

    DATABASE_URL=postgresql://... python -m app.db.migrate

Each file runs once, inside a transaction, and is recorded in
public.schema_migrations. On Supabase you can use `supabase db push` instead;
both read the same files. SQLite demos do not use this (schema comes from ORM).
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg

from app.core.config import get_settings

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "supabase" / "migrations"


def _dsn(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1).replace("postgres://", "postgresql://", 1)


def migration_files(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    return sorted(p for p in directory.glob("*.sql") if p.is_file())


def apply_migrations(database_url: str, directory: Path = MIGRATIONS_DIR) -> list[str]:
    applied: list[str] = []
    with psycopg.connect(_dsn(database_url), autocommit=True) as conn:
        conn.execute(
            "create table if not exists public.schema_migrations "
            "(version text primary key, applied_at timestamptz not null default now())"
        )
        done = {row[0] for row in conn.execute("select version from public.schema_migrations")}
        for path in migration_files(directory):
            if path.name in done:
                continue
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))  # trusted, version-controlled SQL only
                conn.execute("insert into public.schema_migrations (version) values (%s)", (path.name,))
            applied.append(path.name)
    return applied


def main() -> int:
    settings = get_settings()
    if settings.is_sqlite:
        print("DATABASE_URL points to SQLite; migrations are for PostgreSQL. Use the seeder instead.", file=sys.stderr)
        return 1
    applied = apply_migrations(settings.database_url)
    print("Applied: " + (", ".join(applied) if applied else "nothing (up to date)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
