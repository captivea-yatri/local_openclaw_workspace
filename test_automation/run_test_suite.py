#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main test runner — all Odoo RPC scenarios in custom_addons.

Single entry point for listing and running every scenario (role-matrix + scripts).

Usage::

    # List all scenarios (14 unique + duplicates)
    python3 test_automation/run_test_suite.py --list
    python3 -m test_automation --list

    # Smoke: every scenario once (scripts as feature_matrix_tester + Team Manager role)
    python3 test_automation/run_test_suite.py --all \\
        --url http://localhost:8069 --db odoo --user admin --password admin

    # One scenario
    python3 test_automation/run_test_suite.py --scenario so_cancel_old_customer \\
        --mode role --roles-from db --url ... --db ... --user ... --password ...

    # Role-based only: 3 business features × all roles
    python3 test_automation/run_test_suite.py --all --mode role \\
        --roles-from db --url ... --db ... --user ... --password ...

    # Everything: role features × roles + 11 scripts × roles
    python3 test_automation/run_test_suite.py --all --mode full \\
        --roles-from db --url ... --db ... --user ... --password ...

Modes:
    smoke        Each scenario once (default for --all)
    role         Role-matrix business features × all roles
    role-scripts 11 script scenarios × all roles
    full         role + role-scripts (complete matrix)
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
_DIR = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from test_automation.catalog import (  # noqa: E402
    ALL_SCENARIO_IDS,
    DUPLICATE_BY_ID,
    ROLE_MATRIX_SCENARIO_IDS,
    SCRIPT_BY_ID,
    format_catalog_list,
)
from test_automation.matrix_runner import MatrixArgs, run_scenario_matrix, setup_global_mistral_key, setup_matrix_environment  # noqa: E402
from test_automation.paths import ROLES_DATA_XML  # noqa: E402
from test_automation.rpc.role_manager import TEST_USER_LOGIN, TEST_USER_PASSWORD  # noqa: E402
from test_automation.rpc.roles import parse_roles_from_xml, resolve_roles  # noqa: E402
from test_automation.staging import assert_staging_target, load_staging_env  # noqa: E402

DEFAULT_URL = os.environ.get("ODOO_URL", "http://localhost:8069")
DEFAULT_DB = os.environ.get("ODOO_DB", "odoo")
DEFAULT_USER = os.environ.get("ODOO_USER", "admin")
DEFAULT_PASSWORD = os.environ.get("ODOO_PASSWORD", "admin")

MATRIX_RUNNER = _DIR / "run_matrix.py"
FEATURE_MATRIX = _DIR / "run_feature_matrix.py"
ROLE_MATRIX = _DIR / "run_role_matrix.py"
SCRIPT_MATRIX = _DIR / "run_script_matrix.py"

MODES = ("smoke", "role", "role-scripts", "full")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Main runner — all RPC test scenarios",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--list", action="store_true", help="Print scenario catalog")
    p.add_argument(
        "--scenario",
        action="append",
        metavar="NAME",
        help="Scenario id (repeatable)",
    )
    p.add_argument("--all", action="store_true", help="Run all unique scenarios")
    p.add_argument(
        "--mode",
        choices=MODES,
        default="smoke",
        help="smoke=once each; role=business×roles; role-scripts=11×roles; full=role+role-scripts",
    )
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--user", default=DEFAULT_USER, help="Admin for matrix setup (role assignment, cleanup)")
    p.add_argument("--password", default=DEFAULT_PASSWORD)
    p.add_argument(
        "--protocol",
        choices=["jsonrpc", "xmlrpc"],
        default=os.environ.get("ODOO_RPC", "jsonrpc"),
    )
    p.add_argument("--roles-from", choices=["xml", "db"], default="db")
    p.add_argument("--roles-xml", default=str(ROLES_DATA_XML))
    p.add_argument("--roles", nargs="+", metavar="NAME")
    p.add_argument("--no-cleanup", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--report-file", default="")
    p.add_argument("-q", "--quiet", action="store_true")
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
    p.add_argument(
        "--live",
        action="store_true",
        help="Script scenarios: pass --live (e.g. connect_mistral_ai)",
    )
    p.add_argument("--agent-id", type=int, default=None, help="Pass --agent-id to script scenarios")
    p.add_argument(
        "--mistral-key",
        default=os.environ.get("MISTRAL_API_KEY", ""),
        help="Set global Mistral key before matrix (connect_mistral_ai)",
    )
    p.add_argument(
        "--script-extra",
        dest="script_extra_args",
        nargs="*",
        metavar="ARG",
        help="Extra args for script scenarios (matrix/smoke)",
    )
    p.add_argument(
        "--no-project-pm",
        action="store_true",
        help="SO cancel scenario: skip project PM assignment",
    )
    p.add_argument(
        "positional_extra",
        nargs=argparse.REMAINDER,
        help="Legacy: extra args after -- (prefer --script-extra)",
    )
    return p.parse_args()


def print_catalog() -> None:
    print(format_catalog_list())


def _apply_env_from_staging_file(args: argparse.Namespace) -> None:
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


def _build_script_extra_tuple(args: argparse.Namespace) -> tuple[str, ...]:
    extra: list[str] = list(args.script_extra_args or [])
    leg = args.positional_extra or []
    if leg and leg[0] == "--":
        extra.extend(leg[1:])
    elif leg:
        extra.extend(leg)
    if args.live:
        extra = ["--live", *extra]
    if args.agent_id is not None:
        extra = ["--agent-id", str(args.agent_id), *extra]
    # dedupe while preserving order for agent-id/live prepends
    seen: set[str] = set()
    out: list[str] = []
    for item in extra:
        if item not in seen or item.startswith("-"):
            out.append(item)
            if not item.startswith("-"):
                seen.add(item)
    return tuple(out)


def _common_subprocess_args(args: argparse.Namespace) -> list[str]:
    cmd = [
        "--url", args.url,
        "--db", args.db,
        "--user", args.user,
        "--password", args.password,
        "--protocol", args.protocol,
        "--roles-from", args.roles_from,
        "--roles-xml", args.roles_xml,
    ]
    if args.roles:
        cmd.extend(["--roles", *args.roles])
    if args.no_cleanup:
        cmd.append("--no-cleanup")
    if args.strict:
        cmd.append("--strict")
    if args.quiet:
        cmd.append("-q")
    if args.no_project_pm:
        cmd.append("--no-project-pm")
    if args.allow_production:
        cmd.append("--allow-production")
    if args.live:
        cmd.append("--live")
    if args.agent_id is not None:
        cmd.extend(["--agent-id", str(args.agent_id)])
    if args.mistral_key:
        cmd.extend(["--mistral-key", args.mistral_key])
    extra = _build_script_extra_tuple(args)
    if extra:
        cmd.append("--script-extra")
        cmd.extend(extra)
    return cmd


def run_mode_role(args: argparse.Namespace, scenario_filter: list[str] | None) -> int:
    """Business features × roles + optional ACL."""
    if scenario_filter:
        exit_code = 0
        role_only = [s for s in scenario_filter if s in ROLE_MATRIX_SCENARIO_IDS]
        script_only = [s for s in scenario_filter if s in SCRIPT_BY_ID]
        matrix_only = role_only + script_only
        if matrix_only:
            report = args.report_file or "/tmp/suite_role_filter.json"
            cmd = [
                sys.executable, str(MATRIX_RUNNER),
                *_common_subprocess_args(args),
                "--report-file", report,
            ]
            for sid in matrix_only:
                cmd.extend(["--scenario", sid])
            if subprocess.call(cmd) != 0:
                exit_code = 1
        skipped = [s for s in scenario_filter if s not in matrix_only]
        for sid in skipped:
            print(f"SKIP {sid}: unknown or duplicate scenario", file=sys.stderr)
        return exit_code

    report = args.report_file or "/tmp/suite_role_matrix.json"
    cmd = [
        sys.executable,
        str(MATRIX_RUNNER),
        *_common_subprocess_args(args),
        "--report-file",
        report,
    ]
    if scenario_filter:
        for sid in scenario_filter:
            if sid in ROLE_MATRIX_SCENARIO_IDS:
                cmd.extend(["--scenario", sid])
        if not any(s in ROLE_MATRIX_SCENARIO_IDS for s in scenario_filter):
            print("ERROR: no role-matrix scenarios in filter", file=sys.stderr)
            return 2
    else:
        cmd.append("--all-role-matrix")
    return subprocess.call(cmd)


def run_mode_role_scripts(args: argparse.Namespace, scenario_filter: list[str] | None) -> int:
    report = args.report_file or "/tmp/suite_script_matrix.json"
    cmd = [sys.executable, str(MATRIX_RUNNER), *_common_subprocess_args(args), "--report-file", report]
    if scenario_filter:
        for sid in scenario_filter:
            cmd.extend(["--scenario", sid])
    else:
        cmd.append("--all-scripts")
    return subprocess.call(cmd)


def run_mode_full(args: argparse.Namespace, scenario_filter: list[str] | None) -> int:
    exit_code = 0
    role_report = args.report_file or "/tmp/suite_full.json"
    partial_role = "/tmp/suite_full_role.json"
    partial_scripts = "/tmp/suite_full_scripts.json"

    code = run_mode_role(args, scenario_filter if scenario_filter else None)
    if code != 0:
        exit_code = 1
    # Override report for role part
    if Path("/tmp/suite_role_matrix.json").is_file():
        Path(partial_role).write_text(Path("/tmp/suite_role_matrix.json").read_text())

    script_filter = None
    if scenario_filter:
        script_filter = [s for s in scenario_filter if s in SCRIPT_BY_ID]
        if not script_filter:
            script_filter = None
    args_copy_report = argparse.Namespace(**{**vars(args), "report_file": partial_scripts})
    code = run_mode_role_scripts(args_copy_report, script_filter)
    if code != 0:
        exit_code = 1

    combined = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "type": "full",
        "mode": "full",
    }
    if Path(partial_role).is_file():
        combined["role_matrix"] = json.loads(Path(partial_role).read_text())
    if Path(partial_scripts).is_file():
        combined["script_matrix"] = json.loads(Path(partial_scripts).read_text())
    Path(role_report).write_text(json.dumps(combined, indent=2), encoding="utf-8")
    print(f"\nFull report: {role_report}")
    return exit_code


def run_smoke_scenario(sid: str, args: argparse.Namespace) -> int:
    if sid in DUPLICATE_BY_ID:
        dup = DUPLICATE_BY_ID[sid]
        print(f"SKIP {sid}: duplicate of {dup.duplicate_of}")
        return 0

    if sid in ROLE_MATRIX_SCENARIO_IDS or sid in SCRIPT_BY_ID:
        smoke_role = (args.roles or ["Team Manager"])[0]
        matrix_args = MatrixArgs(
            url=args.url,
            db=args.db,
            user=args.user,
            password=args.password,
            protocol=args.protocol,
            roles_from="xml" if not args.roles else args.roles_from,
            roles_xml=args.roles_xml,
            roles=[smoke_role] if not args.roles else args.roles,
            test_login=TEST_USER_LOGIN,
            test_password=TEST_USER_PASSWORD,
            no_cleanup=args.no_cleanup,
            strict=args.strict,
            quiet=args.quiet,
            no_project_pm=args.no_project_pm,
            script_extra=_build_script_extra_tuple(args),
        )
        try:
            admin, role_manager, roles, fallback_partner_id = setup_matrix_environment(
                matrix_args, parse_roles_from_xml, resolve_roles
            )
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        if args.mistral_key and sid == "connect_mistral_ai":
            setup_global_mistral_key(admin, args.mistral_key)
        try:
            rows, failures = run_scenario_matrix(
                sid,
                matrix_args,
                roles=roles[:1] if not args.roles else roles,
                admin=admin,
                role_manager=role_manager,
                fallback_partner_id=fallback_partner_id,
            )
        finally:
            try:
                role_manager.restore_role_lines()
            except Exception:
                pass
        if rows:
            print(f"  Verdict: {rows[0]['verdict']} — {rows[0]['detail']}")
        return 1 if failures else 0

    print(f"ERROR: unknown scenario {sid!r}", file=sys.stderr)
    return 2


def run_mode_smoke(args: argparse.Namespace, scenario_ids: list[str]) -> int:
    results: list[dict] = []
    failures = 0
    for sid in scenario_ids:
        print(f"\n{'=' * 80}\nSMOKE: {sid}\n{'=' * 80}")
        code = run_smoke_scenario(sid, args)
        ok = code == 0
        results.append({"scenario": sid, "exit_code": code, "ok": ok})
        if not ok:
            failures += 1

    print("\n" + "=" * 80)
    print("SMOKE SUMMARY")
    print("=" * 80)
    for row in results:
        status = "PASS" if row["ok"] else "FAIL"
        print(f"  {status}  {row['scenario']}")
    print(f"Failures: {failures}")

    if args.report_file:
        Path(args.report_file).write_text(
            json.dumps({
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "type": "smoke",
                "failures": failures,
                "results": results,
            }, indent=2),
            encoding="utf-8",
        )
    return 1 if failures else 0


def resolve_scenario_ids(args: argparse.Namespace) -> list[str]:
    if args.scenario:
        return args.scenario
    if args.all:
        return list(ALL_SCENARIO_IDS)
    return []


def main() -> int:
    args = parse_args()
    if args.list:
        print_catalog()
        return 0

    if args.load_staging_env:
        load_staging_env()
        _apply_env_from_staging_file(args)

    assert_staging_target(args.url, args.db, allow_production=args.allow_production)

    scenario_ids = resolve_scenario_ids(args)
    if not scenario_ids and not args.all:
        print("ERROR: use --list, --all, or --scenario NAME", file=sys.stderr)
        return 2

    print("=" * 80)
    print("MAIN TEST RUNNER")
    print(f"Mode     : {args.mode}")
    print(f"DB       : {args.db}")
    print(f"URL      : {args.url}")
    if scenario_ids:
        print(f"Scenarios: {', '.join(scenario_ids)}")
    elif args.all:
        print(f"Scenarios: all ({len(ALL_SCENARIO_IDS)})")
    print("=" * 80)

    if args.mode == "role":
        return run_mode_role(args, scenario_ids if args.scenario else None)
    if args.mode == "role-scripts":
        return run_mode_role_scripts(args, scenario_ids if args.scenario else None)
    if args.mode == "full":
        return run_mode_full(args, scenario_ids if args.scenario else None)

    # smoke (default)
    if not scenario_ids:
        scenario_ids = list(ALL_SCENARIO_IDS)
    return run_mode_smoke(args, scenario_ids)


if __name__ == "__main__":
    sys.exit(main())
