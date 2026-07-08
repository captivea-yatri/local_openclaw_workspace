#!/usr/bin/env python3
"""
CAP QA Platform — unified backend + UI + NLP + MCP testing.

Standalone package (does not modify test_automation/).

Examples:
  python3 run_qa.py list
  python3 run_qa.py ask "run smoke so_cancel_old_customer for President"
  python3 run_qa.py backend --scenario so_cancel_old_customer --roles President
  python3 run_qa.py backend --scenario so_cancel_old_customer --roles-from db
  python3 run_qa.py ui --scenario so_cancel_old_customer --role President
  python3 run_qa.py access-ui --roles President "Team Manager"
  python3 run_qa.py full --scenario so_cancel_old_customer --role President
  python3 run_qa.py scaffold my_feature "Brief description of the workflow"
  python3 run_qa.py mcp
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from cap_qa_platform.backend.runner import RunConfig, run_scenario  # noqa: E402
from cap_qa_platform.catalog import ALL_SCENARIO_IDS, list_scenarios  # noqa: E402
from cap_qa_platform.nlp.prompt_cli import (  # noqa: E402
    parse_natural_command,
    print_ask_help,
    scaffold_scenario,
)
from cap_qa_platform.staging import apply_staging_defaults, assert_staging_target, load_staging_env  # noqa: E402
from cap_qa_platform.ui.runner import run_ui_smoke  # noqa: E402


def _conn_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--url", default=os.environ.get("ODOO_URL", "http://localhost:8069"))
    p.add_argument("--db", default=os.environ.get("ODOO_DB", "odoo"))
    p.add_argument("--user", default=os.environ.get("ODOO_USER", "admin"))
    p.add_argument("--password", default=os.environ.get("ODOO_PASSWORD", "admin"))
    p.add_argument(
        "--test-login",
        default=os.environ.get("CAP_QA_TEST_LOGIN", "cap_qa_tester"),
        help="RPC/UI role-test user (default: cap_qa_tester or CAP_QA_TEST_LOGIN)",
    )
    p.add_argument(
        "--test-password",
        default=os.environ.get("CAP_QA_TEST_PASSWORD", "cap_qa_test"),
        help="Password for --test-login (default: cap_qa_test or CAP_QA_TEST_PASSWORD)",
    )
    p.add_argument("--protocol", choices=["jsonrpc", "xmlrpc"], default="jsonrpc")
    p.add_argument("--load-staging-env", action="store_true")
    p.add_argument("--allow-production", action="store_true")
    p.add_argument("--no-cleanup", action="store_true")
    p.add_argument("--strict", action="store_true")


def _cfg_from_args(args) -> RunConfig:
    return RunConfig(
        url=args.url,
        db=args.db,
        user=args.user,
        password=args.password,
        protocol=args.protocol,
        roles_from=getattr(args, "roles_from", "db"),
        roles=getattr(args, "roles", None),
        test_login=getattr(args, "test_login", "cap_qa_tester"),
        test_password=getattr(args, "test_password", "cap_qa_test"),
        no_cleanup=args.no_cleanup,
        strict=args.strict,
    )


def cmd_list(_args) -> int:
    for row in list_scenarios():
        layers = ",".join(row["layers"])
        print(f"  {row['id']:<35} [{row['kind']}] layers={layers}")
        print(f"    {row['description']}")
    print(f"\nTotal: {len(ALL_SCENARIO_IDS)} scenarios")
    return 0


def cmd_backend(args) -> int:
    scenario_ids: list[str] = []
    if getattr(args, "all", False):
        scenario_ids = list(ALL_SCENARIO_IDS)
    elif getattr(args, "scenarios", None):
        scenario_ids = list(args.scenarios)
    elif getattr(args, "scenario", None):
        scenario_ids = [args.scenario]
    else:
        print("ERROR: --scenario, --scenarios, or --all required", file=sys.stderr)
        return 2

    exit_code = 0
    reports = []
    for sid in scenario_ids:
        print(f"\n=== BACKEND: {sid} ===")
        report = run_scenario(_cfg_from_args(args), sid)
        reports.append(report)
        if report["failures"]:
            exit_code = 1
    if len(reports) == 1:
        print(json.dumps(reports[0], indent=2, default=str))
    if args.report_file:
        payload = reports[0] if len(reports) == 1 else reports
        Path(args.report_file).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return exit_code


def cmd_access_ui(args) -> int:
    from cap_qa_platform.paths import ROLES_DATA_XML
    from cap_qa_platform.rpc.client import OdooRPCClient
    from cap_qa_platform.rpc.roles import parse_roles_from_xml
    from cap_qa_platform.ui.access_rights.runner import AccessRightsRoleUITest
    from cap_qa_platform.rpc.role_manager import TEST_USER_LOGIN, TEST_USER_PASSWORD

    roles_xml = getattr(args, "roles_xml", None) or str(ROLES_DATA_XML)
    role_defs = parse_roles_from_xml(Path(roles_xml))
    admin = OdooRPCClient(
        args.url, args.db, args.user, args.password, args.protocol
    )
    try:
        uid = admin.authenticate()
        print(f"Admin authenticated uid={uid}")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    runner = AccessRightsRoleUITest(
        admin=admin,
        url=args.url,
        db=args.db,
        role_defs=role_defs,
        roles_from=args.roles_from,
        role_filter=args.roles,
        test_login=getattr(args, "test_login", TEST_USER_LOGIN),
        test_password=getattr(args, "test_password", TEST_USER_PASSWORD),
        report_file=args.report_file or None,
        verbose=args.verbose,
    )
    return 0 if runner.run() else 1


def cmd_ui(args) -> int:
    os.environ.setdefault("ODOO_URL", args.url)
    os.environ.setdefault("ODOO_DB", args.db)
    os.environ.setdefault("ODOO_USER", args.user)
    os.environ.setdefault("ODOO_PASSWORD", args.password)
    os.environ.setdefault("CAP_QA_TEST_LOGIN", args.test_login)
    os.environ.setdefault("CAP_QA_TEST_PASSWORD", args.test_password)
    if getattr(args, "no_cleanup", False):
        os.environ["CAP_QA_NO_CLEANUP"] = "1"
    if getattr(args, "task_url", None):
        os.environ["CAP_QA_TASK_URL"] = args.task_url
    if getattr(args, "task_id", None):
        os.environ["CAP_QA_TASK_ID"] = str(args.task_id)
    return run_ui_smoke(
        args.scenario, role=args.role, skip_backend=not getattr(args, "with_backend", False)
    )


def cmd_full(args) -> int:
    os.environ.setdefault("ODOO_URL", args.url)
    os.environ.setdefault("ODOO_DB", args.db)
    os.environ.setdefault("ODOO_USER", args.user)
    os.environ.setdefault("ODOO_PASSWORD", args.password)
    os.environ.setdefault("CAP_QA_TEST_LOGIN", args.test_login)
    os.environ.setdefault("CAP_QA_TEST_PASSWORD", args.test_password)
    args.roles = [args.role]
    args.all = False
    args.scenarios = None
    if not getattr(args, "scenario", None):
        args.scenario = "so_cancel_old_customer"
    backend_code = cmd_backend(args)
    ui_code = cmd_ui(args)
    return 1 if backend_code or ui_code else 0


def cmd_ask(args) -> int:
    if not args.prompt:
        print_ask_help()
        return 0
    parsed = parse_natural_command(args.prompt)
    action = parsed.get("action", "smoke")
    scenario = parsed.get("scenario") or args.scenario or "so_cancel_old_customer"
    role = parsed.get("role") or args.role or "President"

    if action == "list":
        return cmd_list(args)
    if action == "scaffold":
        sid = parsed.get("new_scenario_id")
        if not sid:
            print("ERROR: include scenario id, e.g. 'scaffold scenario my_feature that ...'", file=sys.stderr)
            return 2
        result = scaffold_scenario(sid, parsed.get("brief", args.prompt))
        print(json.dumps(result, indent=2))
        return 0

    args.scenario = scenario
    args.role = role
    if action == "matrix":
        args.roles_from = getattr(args, "roles_from", "db")
        args.roles = None
        args.scenarios = None
        args.all = False
        return cmd_backend(args)
    if action == "ui":
        if getattr(args, "no_cleanup", False):
            os.environ["CAP_QA_NO_CLEANUP"] = "1"
        return cmd_ui(args)
    if action == "full":
        return cmd_full(args)
    args.roles = [role]
    args.roles_from = getattr(args, "roles_from", "db")
    args.scenarios = None
    args.all = False
    return cmd_backend(args)


def cmd_scaffold(args) -> int:
    result = scaffold_scenario(args.scenario_id, args.brief, args.modules or [])
    print(json.dumps(result, indent=2))
    return 0


def cmd_discover(_args) -> int:
    from cap_qa_platform.discovery.module_scanner import discover_modules

    print(json.dumps(discover_modules(include_tested=_args.all), indent=2))
    return 0


def cmd_analyze_module(args) -> int:
    from cap_qa_platform.discovery.module_analyzer import analyze_module

    print(json.dumps(analyze_module(args.module), indent=2))
    return 0


def cmd_scaffold_module(args) -> int:
    from cap_qa_platform.discovery.test_generator import scaffold_module_test

    result = scaffold_module_test(
        args.module,
        register_catalog=not args.no_catalog,
        overwrite=args.overwrite,
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_mcp(_args) -> int:
    from cap_qa_platform.mcp.server import _run_mcp

    return _run_mcp()


def main() -> int:
    parser = argparse.ArgumentParser(description="CAP QA Platform — backend + UI + NLP")
    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser("list", help="List catalogued scenarios")
    p_list.set_defaults(func=cmd_list)

    p_backend = sub.add_parser("backend", help="Run backend RPC matrix/smoke")
    _conn_args(p_backend)
    p_backend.add_argument("--scenario", help="Scenario id (repeat for multiple)")
    p_backend.add_argument("--scenarios", nargs="*", help="Alias: multiple scenario ids")
    p_backend.add_argument("--all", action="store_true")
    p_backend.add_argument("--roles", nargs="*")
    p_backend.add_argument("--roles-from", default="db", choices=["xml", "db"])
    p_backend.add_argument("--report-file")
    p_backend.set_defaults(func=cmd_backend)

    p_access_ui = sub.add_parser(
        "access-ui",
        help="Playwright UI smoke for access_rights_management roles",
    )
    _conn_args(p_access_ui)
    p_access_ui.add_argument("--roles", nargs="*")
    p_access_ui.add_argument("--roles-from", default="xml", choices=["xml", "db"])
    p_access_ui.add_argument("--roles-xml", default="")
    p_access_ui.add_argument("--report-file")
    p_access_ui.add_argument("-v", "--verbose", action="store_true")
    p_access_ui.set_defaults(
        func=cmd_access_ui,
    )

    p_ui = sub.add_parser("ui", help="Run UI hybrid smoke")
    _conn_args(p_ui)
    p_ui.add_argument("--scenario", default="so_cancel_old_customer")
    p_ui.add_argument("--role", default="President")
    p_ui.add_argument(
        "--with-backend",
        action="store_true",
        help="Also run backend RPC scenario before UI (default: UI only)",
    )
    p_ui.add_argument(
        "--task-url",
        help="Existing task URL/path for UI scenarios (e.g. /odoo/action-671/217469)",
    )
    p_ui.add_argument("--task-id", type=int, help="Existing project.task id for UI scenarios")
    p_ui.set_defaults(func=cmd_ui)

    p_full = sub.add_parser("full", help="Backend + UI for one scenario/role")
    _conn_args(p_full)
    p_full.add_argument("--scenario", default="so_cancel_old_customer")
    p_full.add_argument("--role", default="President")
    p_full.add_argument("--report-file")
    p_full.set_defaults(func=cmd_full)

    p_ask = sub.add_parser("ask", help="Natural language QA command")
    _conn_args(p_ask)
    p_ask.add_argument("prompt", nargs="?", default="")
    p_ask.add_argument("--scenario")
    p_ask.add_argument("--role", default="President")
    p_ask.add_argument("--roles-from", default="db", choices=["xml", "db"])
    p_ask.add_argument("--report-file")
    p_ask.set_defaults(func=cmd_ask)

    p_scaffold = sub.add_parser("scaffold", help="Create new scenario stub")
    p_scaffold.add_argument("scenario_id")
    p_scaffold.add_argument("brief")
    p_scaffold.add_argument("--modules", nargs="*")
    p_scaffold.set_defaults(func=cmd_scaffold)

    p_discover = sub.add_parser("discover", help="Scan custom_addons for QA coverage gaps")
    p_discover.add_argument("--all", action="store_true", help="Include modules already in catalog")
    p_discover.set_defaults(func=cmd_discover)

    p_analyze = sub.add_parser("analyze-module", help="Analyze one Odoo module folder")
    p_analyze.add_argument("module")
    p_analyze.set_defaults(func=cmd_analyze_module)

    p_scaffold_mod = sub.add_parser("scaffold-module", help="Auto-generate RPC smoke test for a module")
    p_scaffold_mod.add_argument("module")
    p_scaffold_mod.add_argument("--no-catalog", action="store_true")
    p_scaffold_mod.add_argument("--overwrite", action="store_true")
    p_scaffold_mod.set_defaults(func=cmd_scaffold_module)

    p_mcp = sub.add_parser("mcp", help="Start MCP server for AI tools")
    p_mcp.set_defaults(func=cmd_mcp)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 0

    if getattr(args, "load_staging_env", False):
        load_staging_env()
    apply_staging_defaults(args, load_env=False)
    if hasattr(args, "url") and hasattr(args, "db"):
        assert_staging_target(
            args.url,
            args.db,
            allow_production=getattr(args, "allow_production", False),
        )

    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
