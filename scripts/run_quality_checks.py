#!/usr/bin/env python3
"""Run every local quality gate and print a summary.

    python3 scripts/run_quality_checks.py            # backend + frontend
    python3 scripts/run_quality_checks.py --backend-only

PostgreSQL tests run only when TEST_DATABASE_URL is set.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "backend" / ".venv" / "bin" / "python"


def checks(backend_only: bool) -> list[tuple[str, list[str], Path]]:
    backend = ROOT / "backend"
    frontend = ROOT / "frontend"
    items = [
        ("ruff lint", [str(PY), "-m", "ruff", "check", "app", "tests"], backend),
        ("ruff format", [str(PY), "-m", "ruff", "format", "--check", "app", "tests"], backend),
        ("synthetic data validation", [str(PY), str(ROOT / "scripts" / "validate_synthetic_data.py")], ROOT),
        ("backend tests", [str(PY), "-m", "pytest", "-q", "-p", "no:cacheprovider"], backend),
    ]
    if not backend_only:
        items += [
            ("frontend typecheck", ["npm", "run", "typecheck"], frontend),
            ("frontend lint", ["npm", "run", "lint"], frontend),
            ("frontend build", ["npm", "run", "build"], frontend),
        ]
    return items


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-only", action="store_true")
    args = parser.parse_args()
    results = []
    for name, command, cwd in checks(args.backend_only):
        print(f"\n=== {name} ===", flush=True)
        code = subprocess.call(command, cwd=cwd)  # noqa: S603 - fixed, trusted commands
        results.append((name, code))
    print("\nSummary")
    for name, code in results:
        print(f"  {'PASS' if code == 0 else 'FAIL'}  {name}")
    return 0 if all(code == 0 for _, code in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
