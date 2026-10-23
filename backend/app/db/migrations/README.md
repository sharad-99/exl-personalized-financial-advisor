# Migrations

The SQL migrations live in [`supabase/migrations/`](../../../../supabase/migrations) so that the
Supabase CLI (`supabase db push`) and the backend runner (`python -m app.db.migrate`) apply the
same files. Files are applied once each, in filename order, and are written to be re-runnable.

- `..._initial_schema.sql` — tables, constraints, indexes, triggers
- `..._row_level_security.sql` — RLS policies and least-privilege grants
- `..._reference_data.sql` — generated from `app/synthetic_data/reference_data.py`

SQLite (local demo) does not use these files: its schema comes from the ORM models, and
`tests/integration/test_schema_parity.py` checks both stay aligned.
