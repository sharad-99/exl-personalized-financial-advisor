#!/usr/bin/env python3
"""Generate the synthetic dataset in memory and validate it.

Exits non-zero if any invalid record or financial inconsistency is found.

    backend/.venv/bin/python scripts/validate_synthetic_data.py --seed 42
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.synthetic_data.generator import generate_dataset  # noqa: E402
from app.synthetic_data.validation import validate_dataset  # noqa: E402
from app.utils.dates import utc_today  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--as-of", type=date.fromisoformat, default=None)
    parser.add_argument("--customers", type=int, default=None)
    args = parser.parse_args()

    dataset = generate_dataset(seed=args.seed, as_of=args.as_of or utc_today(), customer_count=args.customers)
    report = validate_dataset(dataset)
    print(f"Synthetic dataset seed={dataset.seed} as_of={dataset.as_of}: {report.stats}")
    for warning in report.warnings:
        print(f"  WARNING  {warning}")
    for error in report.errors:
        print(f"  ERROR    {error}")
    print("RESULT: " + ("PASS" if report.ok else f"FAIL ({len(report.errors)} errors)"))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
