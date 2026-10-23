#!/usr/bin/env python3
"""Export the reproducible SYNTHETIC dataset to CSV and JSON files.

    backend/.venv/bin/python scripts/generate_synthetic_data.py --seed 42 --as-of 2026-10-24 --out data/generated

To load data into a database use the seeder instead:
    cd backend && .venv/bin/python -m app.synthetic_data.seed --seed 42 --reset
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.synthetic_data.generator import generate_dataset  # noqa: E402
from app.utils.dates import utc_today  # noqa: E402

TABLES = ("profiles", "financial_profiles", "accounts", "transactions", "goals", "obligations")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--as-of", type=date.fromisoformat, default=None)
    parser.add_argument("--customers", type=int, default=None)
    parser.add_argument("--out", type=Path, default=Path("data/generated"))
    args = parser.parse_args()

    dataset = generate_dataset(seed=args.seed, as_of=args.as_of or utc_today(), customer_count=args.customers)
    args.out.mkdir(parents=True, exist_ok=True)
    for table in TABLES:
        rows = getattr(dataset, table)
        with (args.out / f"{table}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        (args.out / f"{table}.json").write_text(json.dumps(rows, default=str, indent=1), encoding="utf-8")
    manifest = {
        "notice": "SYNTHETIC DATA - fabricated for an academic demo; not real bank or customer data.",
        "seed": dataset.seed,
        "as_of": dataset.as_of.isoformat(),
        "generator_version": dataset.generator_version,
        "counts": {t: len(getattr(dataset, t)) for t in TABLES},
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {manifest['counts']} to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
