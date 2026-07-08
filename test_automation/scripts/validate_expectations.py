#!/usr/bin/env python3
"""Check expectations cover all roles from a matrix report or list roles gaps."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from test_automation.catalog import ALL_SCENARIO_IDS  # noqa: E402
from test_automation.matrix_runner import load_expectations  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Validate expectations completeness")
    p.add_argument("--roles-file", type=Path, help="JSON list of role names or matrix report")
    p.add_argument("--scenario", action="append", help="Scenario id (default: all)")
    p.add_argument("--strict", action="store_true", help="Exit 1 if any role unlisted")
    args = p.parse_args()

    scenario_ids = args.scenario or list(ALL_SCENARIO_IDS)
    all_roles: set[str] = set()

    if args.roles_file and args.roles_file.is_file():
        data = json.loads(args.roles_file.read_text(encoding="utf-8"))
        if isinstance(data, list):
            all_roles = {str(x) for x in data}
        elif "roles" in data and isinstance(data["roles"], list):
            for row in data["roles"]:
                name = row.get("role") or row.get("role_name")
                if name:
                    all_roles.add(name)

    exit_code = 0
    for sid in scenario_ids:
        try:
            exp = load_expectations(sid)
        except FileNotFoundError as exc:
            print(f"FAIL {sid}: {exc}")
            exit_code = 1
            continue

        full = set(exp.get("full_access") or [])
        blocked = set((exp.get("blocked") or {}).keys())
        covered = full | blocked
        unlisted = all_roles - covered if all_roles else set()

        print(f"\n{sid}")
        print(f"  full_access : {len(full)}")
        print(f"  blocked     : {len(blocked)}")
        if all_roles:
            print(f"  unlisted    : {len(unlisted)}")
            if unlisted and args.strict:
                exit_code = 1
                for name in sorted(unlisted)[:20]:
                    print(f"    - {name}")
                if len(unlisted) > 20:
                    print(f"    ... and {len(unlisted) - 20} more")
        elif not full and not blocked:
            print("  WARN: empty expectations (all runs will be REPORT)")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
