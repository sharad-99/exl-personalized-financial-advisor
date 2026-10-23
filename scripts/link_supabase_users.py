#!/usr/bin/env python3
"""Link Supabase Auth users to synthetic demo profiles by email.

Each Supabase user created in the dashboard (e.g. customer01@demo.exl.test) is linked to the
synthetic profile with the same email by setting profiles.auth_user_id. Only synthetic profiles
are touched. Run with the project owner connection string (never the exl_api role):

    cd backend
    set -a; . ./.env.supabase; set +a
    .venv/bin/python ../scripts/link_supabase_users.py            # dry run
    .venv/bin/python ../scripts/link_supabase_users.py --apply

The seeder preserves these links across `--reset`.
"""

from __future__ import annotations

import argparse
import os
import sys

import psycopg

PREVIEW = """
select u.email, u.id, p.id, p.role, p.auth_user_id
from auth.users u
left join public.profiles p on p.email = lower(u.email) and p.is_synthetic
order by u.email
"""
APPLY = """
update public.profiles p
set auth_user_id = u.id
from auth.users u
where p.email = lower(u.email) and p.is_synthetic and p.auth_user_id is distinct from u.id
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Write the links (default: dry run)")
    args = parser.parse_args()
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgres"):
        print("Set DATABASE_URL to the Supabase (owner) connection string.", file=sys.stderr)
        return 2
    with psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://")) as conn:
        rows = conn.execute(PREVIEW).fetchall()
        if not rows:
            print("No Supabase Auth users found. Create them under Authentication -> Users first.")
            return 1
        for email, _auth_id, profile_id, role, linked in rows:
            if profile_id is None:
                state = "no synthetic profile with this email (skipped)"
            elif linked is not None and str(linked) == str(_auth_id):
                state = f"already linked ({role})"
            else:
                state = f"will link to {role} profile" if not args.apply else f"linked ({role})"
            print(f"  {email:<32} {state}")
        if args.apply:
            changed = conn.execute(APPLY).rowcount
            conn.commit()
            print(f"Updated {changed} profile(s).")
        else:
            print("Dry run only. Re-run with --apply to write the links.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
