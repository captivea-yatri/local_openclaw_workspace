#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run the complete test matrix: 11 script scenarios × roles + 3 role-matrix scenarios × roles.

    python3 test_automation/run_full_matrix.py \\
        --roles-from db \\
        --url http://localhost:8069 --db odoo --user admin --password admin \\
        --report-file /tmp/full_matrix.json
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

SCRIPT_MATRIX = Path(__file__).resolve().parent / "run_script_matrix.py"
FEATURE_MATRIX = Path(__file__).resolve().parent / "run_feature_matrix.py"

from test_automation.catalog import ROLE_MATRIX_SCENARIO_IDS  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Full matrix: 11 scripts + 3 role flows × roles")
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
    p.add_argument("--roles", nargs="+", metavar="NAME")
    p.add_argument("--no-cleanup", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--report-file", default="")
    p.add_argument("--skip-script-matrix", action="store_true")
    p.add_argument("--skip-role-matrix", action="store_true")
    p.add_argument("-q", "--quiet", action="store_true")
    return p.parse_args()


def _base_cmd(args: argparse.Namespace, script: Path) -> list[str]:
    cmd = [
        sys.executable,
        str(script),
        "--url", args.url,
        "--db", args.db,
        "--user", args.user,
        "--password", args.password,
        "--protocol", args.protocol,
        "--roles-from", args.roles_from,
    ]
    if args.roles:
        cmd.extend(["--roles", *args.roles])
    if args.no_cleanup:
        cmd.append("--no-cleanup")
    if args.strict:
        cmd.append("--strict")
    if args.quiet:
        cmd.append("-q")
    return cmd


def main() -> int:
    args = parse_args()
    exit_code = 0
    sections: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "type": "full_matrix",
        "db": args.db,
        "url": args.url,
    }

    if not args.skip_script_matrix:
        print("\n>>> SCRIPT MATRIX (12 scenarios × roles)\n")
        sm_report = "/tmp/script_matrix_partial.json"
        cmd = _base_cmd(args, SCRIPT_MATRIX)
        cmd.extend(["--report-file", sm_report])
        code = subprocess.call(cmd)
        if code != 0:
            exit_code = 1
        if Path(sm_report).is_file():
            sections["script_matrix"] = json.loads(Path(sm_report).read_text())

    if not args.skip_role_matrix:
        role_reports = {}
        for scenario in ROLE_MATRIX_SCENARIO_IDS:
            print(f"\n>>> ROLE MATRIX: {scenario}\n")
            rm_report = f"/tmp/role_matrix_{scenario}.json"
            cmd = _base_cmd(args, FEATURE_MATRIX)
            cmd.extend(["--scenario", scenario, "--report-file", rm_report])
            code = subprocess.call(cmd)
            if code != 0:
                exit_code = 1
            if Path(rm_report).is_file():
                role_reports[scenario] = json.loads(Path(rm_report).read_text())
        sections["role_matrix"] = role_reports

    if args.report_file:
        Path(args.report_file).write_text(json.dumps(sections, indent=2), encoding="utf-8")
        print(f"\nFull report: {args.report_file}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
