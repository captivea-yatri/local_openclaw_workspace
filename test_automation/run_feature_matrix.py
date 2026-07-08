#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Feature matrix runner — business scenarios × all roles (Odoo 19 RPC).

Runs a business-flow scenario once per role from access_rights_management/data/roles_data.xml
using a dedicated test user (base_user_role). Compares outcomes to expectations JSON.

First scenario: SO cancel → old_customer (cap_partner + ksc_sale_project_extended + …).

Usage::

    # All roles, SO cancel scenario, staging
    python3 test_automation/run_feature_matrix.py \\
        --url https://staging-odoo19-captivea.odoo.com/ \\
        --db captivea-staging-odoo19-33645016 \\
        --user yatri.modi@captivea.com \\
        --password a \\
        --scenario so_cancel_old_customer \\
        --no-cleanup \\
        --report-file /tmp/feature_matrix.json

    # Subset of roles (faster)
    python3 test_automation/run_feature_matrix.py \\
        --scenario so_cancel_old_customer \\
        --roles President "Sales Manager" HR \\
        --url ... --db ... --user ... --password ...
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow imports when executed as: python3 test_automation/run_feature_matrix.py
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from test_automation.matrix_runner import MatrixArgs, load_expectations, run_scenario_matrix, setup_matrix_environment
from test_automation.paths import ROLES_DATA_XML
from test_automation.rpc.role_manager import (
    TEST_USER_LOGIN,
    TEST_USER_PASSWORD,
)
from test_automation.rpc.roles import parse_roles_from_xml, resolve_roles

DEFAULT_URL = os.environ.get("ODOO_URL", "http://localhost:8069")
DEFAULT_DB = os.environ.get("ODOO_DB", "odoo")
DEFAULT_USER = os.environ.get("ODOO_USER", "admin")
DEFAULT_PASSWORD = os.environ.get("ODOO_PASSWORD", "admin")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Feature matrix: business scenarios × all roles",
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--user", default=DEFAULT_USER, help="Admin user for setup")
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument(
        "--protocol",
        choices=["jsonrpc", "xmlrpc"],
        default=os.environ.get("ODOO_RPC", "jsonrpc"),
    )
    parser.add_argument(
        "--scenario",
        default="so_cancel_old_customer",
        help="Scenario name (see test_automation/scenarios/)",
    )
    parser.add_argument(
        "--expectations",
        default="",
        help="Path to expectations JSON (default: expectations/<scenario>.json)",
    )
    parser.add_argument(
        "--roles-from",
        choices=["xml", "db"],
        default="xml",
    )
    parser.add_argument(
        "--roles-xml",
        default=str(ROLES_DATA_XML),
    )
    parser.add_argument(
        "--roles",
        nargs="+",
        metavar="NAME",
        help="Test only these role names",
    )
    parser.add_argument("--test-login", default=TEST_USER_LOGIN)
    parser.add_argument("--test-password", default=TEST_USER_PASSWORD)
    parser.add_argument("--no-cleanup", action="store_true")
    parser.add_argument(
        "--no-project-pm",
        action="store_true",
        help="Do not set project.user_id before cancel",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if any unlisted role does not complete the flow",
    )
    parser.add_argument("--report-file", default="", help="Write JSON report path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    expectations_path = Path(args.expectations) if args.expectations else None
    expectations = load_expectations(args.scenario, expectations_path)

    print("=" * 80)
    print("FEATURE MATRIX — business scenario × roles")
    print(f"Scenario    : {args.scenario}")
    print(f"Modules     : {', '.join(expectations.get('modules', []))}")
    print(f"DB          : {args.db}")
    print(f"URL         : {args.url}")
    print(f"Roles from  : {args.roles_from}")
    print("=" * 80)

    matrix_args = MatrixArgs(
        url=args.url,
        db=args.db,
        user=args.user,
        password=args.password,
        protocol=args.protocol,
        roles_from=args.roles_from,
        roles_xml=args.roles_xml,
        roles=args.roles,
        test_login=args.test_login,
        test_password=args.test_password,
        no_cleanup=args.no_cleanup,
        strict=args.strict,
        quiet=False,
        no_project_pm=args.no_project_pm,
    )

    try:
        admin, role_manager, roles, fallback_partner_id = setup_matrix_environment(
            matrix_args, parse_roles_from_xml, resolve_roles
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Admin fallback partner id={fallback_partner_id} (used when role cannot create partners)")

    try:
        role_results, failures = run_scenario_matrix(
            args.scenario,
            matrix_args,
            roles=roles,
            admin=admin,
            role_manager=role_manager,
            fallback_partner_id=fallback_partner_id,
            expectations=expectations,
        )
    finally:
        print("\n--- Restoring test user roles ---")
        try:
            role_manager.restore_role_lines()
            print("  Done.")
        except Exception as exc:
            print(f"  [WARN] {exc}")

    for row in role_results:
        print(f"\n--- Role: {row['role']} ---")
        print(f"  Verdict: {row['verdict']} — {row['detail']}")
        if row.get("records"):
            print(f"  Records: {row['records']}")

    # Summary table
    print("\n" + "=" * 80)
    print("FEATURE MATRIX SUMMARY")
    print("=" * 80)
    print(f"{'Role':<32} {'Verdict':<14} Detail")
    print("-" * 80)
    for row in role_results:
        detail = (row["detail"] or "")[:42]
        print(f"{row['role']:<32} {row['verdict']:<14} {detail}")

    counts: dict[str, int] = {}
    for row in role_results:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    print("-" * 80)
    print("Counts:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario": args.scenario,
        "db": args.db,
        "url": args.url,
        "modules": expectations.get("modules"),
        "role_count": len(role_results),
        "failures": failures,
        "counts": counts,
        "roles": role_results,
    }
    if args.report_file:
        out = Path(args.report_file)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nReport written: {out}")

    exit_code = 1 if failures else 0

    print("=" * 80)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
