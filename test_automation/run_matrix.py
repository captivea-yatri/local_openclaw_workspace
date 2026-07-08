#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified matrix runner — all registered scenarios × all roles.

Portable entry point for the migratable test_automation package.

Usage::

    # One scenario × all roles
    python3 test_automation/run_matrix.py --scenario so_cancel_old_customer \\
        --roles-from db --url ... --db ... --user ... --password ...

    # All 14 scenarios × all roles (long)
    python3 test_automation/run_matrix.py --all \\
        --roles-from db --url ... --db ... --user ... --password ...

    # Script scenarios only
    python3 test_automation/run_matrix.py --all-scripts \\
        --roles-from db --url ... --db ... --user ... --password ...
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from test_automation.catalog import ALL_SCENARIO_IDS, ROLE_MATRIX_SCENARIO_IDS, SCRIPT_BY_ID  # noqa: E402
from test_automation.matrix_runner import (  # noqa: E402
    MatrixArgs,
    run_scenario_matrix,
    run_scenarios_matrix,
    setup_global_mistral_key,
    setup_matrix_environment,
)
from test_automation.paths import ROLES_DATA_XML  # noqa: E402
from test_automation.rpc.role_manager import TEST_USER_LOGIN, TEST_USER_PASSWORD  # noqa: E402
from test_automation.rpc.roles import parse_roles_from_xml, resolve_roles  # noqa: E402
from test_automation.staging import assert_staging_target, load_staging_env  # noqa: E402
from test_automation.scenarios.registry import list_scenario_ids  # noqa: E402

DEFAULT_URL = os.environ.get("ODOO_URL", "http://localhost:8069")
DEFAULT_DB = os.environ.get("ODOO_DB", "odoo")
DEFAULT_USER = os.environ.get("ODOO_USER", "admin")
DEFAULT_PASSWORD = os.environ.get("ODOO_PASSWORD", "admin")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Unified scenario matrix × roles")
    p.add_argument("--scenario", action="append", metavar="NAME", help="Scenario id (repeatable)")
    p.add_argument("--all", action="store_true", help="All 15 unique scenarios")
    p.add_argument("--all-scripts", action="store_true", help="All 11 script scenarios")
    p.add_argument("--all-role-matrix", action="store_true", help="All 3 role-matrix scenarios")
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--user", default=DEFAULT_USER)
    p.add_argument("--password", default=DEFAULT_PASSWORD)
    p.add_argument(
        "--protocol",
        choices=["jsonrpc", "xmlrpc"],
        default=os.environ.get("ODOO_RPC", "jsonrpc"),
    )
    p.add_argument("--roles-from", choices=["xml", "db"], default="db")
    p.add_argument("--roles-xml", default=str(ROLES_DATA_XML))
    p.add_argument("--roles", nargs="+", metavar="NAME")
    p.add_argument("--test-login", default=TEST_USER_LOGIN)
    p.add_argument("--test-password", default=TEST_USER_PASSWORD)
    p.add_argument("--no-cleanup", action="store_true")
    p.add_argument("--no-project-pm", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--report-file", default="")
    p.add_argument("-q", "--quiet", action="store_true")
    p.add_argument(
        "--live",
        action="store_true",
        help="Script scenarios: run with --live (e.g. connect_mistral_ai Mistral API calls)",
    )
    p.add_argument(
        "--agent-id",
        type=int,
        default=None,
        help="Script scenarios: pass --agent-id to bundled script (e.g. connect_mistral_ai)",
    )
    p.add_argument(
        "--mistral-key",
        default=os.environ.get("MISTRAL_API_KEY", ""),
        help="Set connect_mistral_ai.mistral_key once via admin before matrix (not passed to role users)",
    )
    p.add_argument(
        "--script-extra",
        nargs="*",
        metavar="ARG",
        help="More args for script scenarios (place last), e.g. --script-extra --custom-only",
    )
    p.add_argument(
        "--load-staging-env",
        action="store_true",
        help="Load test_automation/staging.env before run",
    )
    p.add_argument(
        "--allow-production",
        action="store_true",
        help="Skip production URL/DB guard (emergency only)",
    )
    return p.parse_args()


def resolve_scenarios(args: argparse.Namespace) -> list[str]:
    if args.scenario:
        return args.scenario
    if args.all:
        return list(ALL_SCENARIO_IDS)
    if args.all_scripts:
        return list(SCRIPT_BY_ID.keys())
    if args.all_role_matrix:
        return list(ROLE_MATRIX_SCENARIO_IDS)
    return ["so_cancel_old_customer"]


def main() -> int:
    args = parse_args()
    if args.load_staging_env:
        load_staging_env()
        if os.environ.get("ODOO_URL"):
            args.url = os.environ["ODOO_URL"]
        if os.environ.get("ODOO_DB"):
            args.db = os.environ["ODOO_DB"]
        if os.environ.get("ODOO_USER"):
            args.user = os.environ["ODOO_USER"]
        if os.environ.get("ODOO_PASSWORD"):
            args.password = os.environ["ODOO_PASSWORD"]
        if os.environ.get("ODOO_RPC"):
            args.protocol = os.environ["ODOO_RPC"]

    assert_staging_target(args.url, args.db, allow_production=args.allow_production)

    scenario_ids = resolve_scenarios(args)
    script_extra = tuple(args.script_extra or [])
    if args.live:
        script_extra = ("--live",) + script_extra
    if args.agent_id is not None:
        script_extra = ("--agent-id", str(args.agent_id)) + script_extra

    for sid in scenario_ids:
        if sid not in list_scenario_ids():
            print(f"ERROR: unknown scenario {sid!r}", file=sys.stderr)
            return 2

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
        quiet=args.quiet,
        no_project_pm=args.no_project_pm,
        script_extra=script_extra,
    )

    print("=" * 80)
    print("UNIFIED MATRIX RUNNER")
    print(f"Scenarios : {', '.join(scenario_ids)}")
    print(f"DB        : {args.db}")
    print(f"URL       : {args.url}")
    print(f"Roles from: {args.roles_from}")
    print("=" * 80)

    try:
        admin, role_manager, roles, fallback_partner_id = setup_matrix_environment(
            matrix_args, parse_roles_from_xml, resolve_roles
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Admin fallback partner id={fallback_partner_id}")

    if args.mistral_key and "connect_mistral_ai" in scenario_ids:
        setup_global_mistral_key(admin, args.mistral_key)
        print("Mistral API key set server-side (ir.config_parameter) — role users do not need Settings access")

    failures = 0
    all_rows: list[dict] = []

    try:
        if len(scenario_ids) == 1:
            sid = scenario_ids[0]
            print(f"\n--- Scenario: {sid} ({len(roles)} roles) ---")
            rows, failures = run_scenario_matrix(
                sid,
                matrix_args,
                roles=roles,
                admin=admin,
                role_manager=role_manager,
                fallback_partner_id=fallback_partner_id,
            )
            all_rows = rows
            for row in rows:
                print(f"  {row['role']:<32} {row['verdict']:<14} {(row['detail'] or '')[:50]}")
        else:
            report = run_scenarios_matrix(
                scenario_ids,
                matrix_args,
                roles=roles,
                admin=admin,
                role_manager=role_manager,
                fallback_partner_id=fallback_partner_id,
            )
            all_rows = report["results"]
            failures = report["failures"]
            for sid in scenario_ids:
                sub = [r for r in all_rows if r.get("scenario") == sid]
                counts: dict[str, int] = {}
                for row in sub:
                    counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
                parts = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
                print(f"  {sid}: {parts}")
    finally:
        print("\n--- Restoring test user roles ---")
        try:
            role_manager.restore_role_lines()
            print("  Done.")
        except Exception as exc:
            print(f"  [WARN] {exc}")

    counts: dict[str, int] = {}
    for row in all_rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1

    print("\n" + "=" * 80)
    print("MATRIX SUMMARY")
    print("-" * 80)
    print("Counts:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"Failures (FAIL verdict): {failures}")
    print("=" * 80)

    if args.report_file:
        from datetime import datetime, timezone

        out = Path(args.report_file)
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scenarios": scenario_ids,
            "role_count": len(roles),
            "failures": failures,
            "counts": counts,
            "roles": all_rows,
            "db": args.db,
            "url": args.url,
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Report written: {out}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
