#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Role-based testing — all business feature scenarios × all roles.

Runs feature-matrix scenarios (RPC as feature_matrix_tester per role):
  - so_cancel_old_customer
  - so_link_project_invoice_color
  - quality_issue_ask_for_review

Usage::

    python3 test_automation/run_role_matrix.py \\
        --roles-from db \\
        --url http://localhost:8069 --db odoo --user admin --password admin \\
        --report-file /tmp/role_matrix_all.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

FEATURE_MATRIX = Path(__file__).resolve().parent / "run_feature_matrix.py"

from test_automation.catalog import ROLE_MATRIX_SCENARIO_IDS  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Role-based: all feature-matrix scenarios × roles",
    )
    p.add_argument("--url", default=os.environ.get("ODOO_URL", "http://localhost:8069"))
    p.add_argument("--db", default=os.environ.get("ODOO_DB", "odoo"))
    p.add_argument("--user", default=os.environ.get("ODOO_USER", "admin"))
    p.add_argument("--password", default=os.environ.get("ODOO_PASSWORD", "admin"))
    p.add_argument(
        "--protocol",
        choices=["jsonrpc", "xmlrpc"],
        default=os.environ.get("ODOO_RPC", "jsonrpc"),
    )
    p.add_argument("--roles-from", choices=["xml", "db"], default="db")
    p.add_argument("--roles", nargs="+", metavar="NAME", help="Subset of role names")
    p.add_argument("--no-cleanup", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--report-file", default="")
    return p.parse_args()


def _feature_matrix_cmd(args: argparse.Namespace, scenario: str, report: str) -> list[str]:
    cmd = [
        sys.executable,
        str(FEATURE_MATRIX),
        "--scenario", scenario,
        "--url", args.url,
        "--db", args.db,
        "--user", args.user,
        "--password", args.password,
        "--protocol", args.protocol,
        "--roles-from", args.roles_from,
        "--report-file", report,
    ]
    if args.roles:
        cmd.extend(["--roles", *args.roles])
    if args.no_cleanup:
        cmd.append("--no-cleanup")
    if args.strict:
        cmd.append("--strict")
    return cmd


def main() -> int:
    args = parse_args()
    exit_code = 0
    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "type": "role_matrix_only",
        "db": args.db,
        "url": args.url,
        "roles_from": args.roles_from,
        "feature_scenarios": list(ROLE_MATRIX_SCENARIO_IDS),
        "features": {},
    }

    print("=" * 80)
    print("ROLE MATRIX — business features × roles")
    print(f"Features: {', '.join(ROLE_MATRIX_SCENARIO_IDS)}")
    print(f"Roles from: {args.roles_from}")
    print("=" * 80)

    for scenario in ROLE_MATRIX_SCENARIO_IDS:
        partial = f"/tmp/role_matrix_{scenario}.json"
        print(f"\n>>> Feature: {scenario} (per role)\n")
        code = subprocess.call(_feature_matrix_cmd(args, scenario, partial))
        if code != 0:
            exit_code = 1
        if Path(partial).is_file():
            report["features"][scenario] = json.loads(Path(partial).read_text())

    if args.report_file:
        Path(args.report_file).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nCombined report: {args.report_file}")

    print("\n" + "=" * 80)
    print("ROLE MATRIX — finished" + (" (failures)" if exit_code else " (ok)"))
    print("=" * 80)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
