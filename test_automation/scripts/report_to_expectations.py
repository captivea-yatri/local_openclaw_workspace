#!/usr/bin/env python3
"""Build or update expectations JSON from a matrix report file."""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from test_automation.matrix_runner import load_expectations  # noqa: E402
from test_automation.paths import EXPECTATIONS, EXPECTATIONS_SCRIPTS  # noqa: E402
from test_automation.rpc.errors import is_access_error  # noqa: E402
from test_automation.scenarios.registry import is_script_scenario  # noqa: E402


def _iter_role_rows(report: dict, scenario_id: str) -> list[dict]:
    """Extract flat role result rows for one scenario from various report shapes."""
    if "roles" in report and isinstance(report["roles"], list):
        rows = report["roles"]
        if rows and rows[0].get("scenario") == scenario_id:
            return [r for r in rows if r.get("scenario") == scenario_id]
        if report.get("scenario") == scenario_id or not rows[0].get("scenario"):
            return rows

    if "results" in report:
        return [r for r in report["results"] if r.get("scenario") == scenario_id]

    if "features" in report and scenario_id in report["features"]:
        feat = report["features"][scenario_id]
        return feat.get("roles") or []

    if report.get("scenario") == scenario_id:
        return report.get("roles") or []

    return []


def propose_expectations(
    scenario_id: str,
    rows: list[dict],
    existing: dict,
) -> dict:
    out = deepcopy(existing)
    out["scenario"] = scenario_id
    full_access: list[str] = list(out.get("full_access") or [])
    blocked: dict = dict(out.get("blocked") or {})

    full_set = set(full_access)
    blocked_names = set(blocked)

    for row in rows:
        role = row.get("role") or row.get("role_name")
        if not role:
            continue
        success = row.get("success")
        if success is None:
            success = row.get("verdict") in ("PASS", "REPORT") and not row.get("error")
        failed_step = row.get("failed_step") or "script"
        error = row.get("error") or row.get("detail") or ""

        if success:
            if role not in blocked_names:
                full_set.add(role)
        elif is_access_error(Exception(str(error))):
            blocked[role] = {"at": failed_step or "script", "error": "AccessError"}
            blocked_names.add(role)
            full_set.discard(role)
        # Non-access failures: leave for manual review (not auto-blocked)

    out["full_access"] = sorted(full_set)
    out["blocked"] = dict(sorted(blocked.items()))
    return out


def expectations_path(scenario_id: str) -> Path:
    if is_script_scenario(scenario_id):
        return EXPECTATIONS_SCRIPTS / f"{scenario_id}.json"
    return EXPECTATIONS / f"{scenario_id}.json"


def main() -> int:
    p = argparse.ArgumentParser(description="Update expectations from matrix JSON report")
    p.add_argument("--report", required=True, type=Path, help="Matrix report JSON path")
    p.add_argument("--scenario", required=True, help="Scenario id")
    p.add_argument("--write", action="store_true", help="Write expectations file")
    p.add_argument("--dry-run", action="store_true", help="Print proposed JSON only")
    args = p.parse_args()

    if not args.report.is_file():
        print(f"ERROR: report not found: {args.report}", file=sys.stderr)
        return 1

    report = json.loads(args.report.read_text(encoding="utf-8"))
    rows = _iter_role_rows(report, args.scenario)
    if not rows:
        print(f"ERROR: no role rows for scenario {args.scenario!r} in report", file=sys.stderr)
        return 1

    try:
        existing = load_expectations(args.scenario)
    except FileNotFoundError:
        existing = {"scenario": args.scenario, "full_access": [], "blocked": {}}

    proposed = propose_expectations(args.scenario, rows, existing)
    text = json.dumps(proposed, indent=2, ensure_ascii=False) + "\n"

    if args.dry_run or not args.write:
        print(text)
        if not args.write:
            print(
                f"# Proposed from {len(rows)} rows. Re-run with --write to save "
                f"{expectations_path(args.scenario)}",
                file=sys.stderr,
            )
        return 0

    dest = expectations_path(args.scenario)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    print(f"Wrote {dest} ({len(proposed['full_access'])} full_access, {len(proposed['blocked'])} blocked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
