"""Backend matrix and smoke execution."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cap_qa_platform.backend.script_runner import run_script
from cap_qa_platform.catalog import ROLE_MATRIX_BY_ID, SCRIPT_BY_ID, ScenarioEntry, get_entry
from cap_qa_platform.matrix_common import classify_matrix_outcome
from cap_qa_platform.paths import EXPECTATIONS_DIR
from cap_qa_platform.rpc.client import OdooRPCClient, m2o_id
from cap_qa_platform.rpc.role_manager import RoleManager, TEST_USER_LOGIN, TEST_USER_PASSWORD
from cap_qa_platform.rpc.roles import parse_roles_from_xml, resolve_roles
from cap_qa_platform.scenarios.base import ScenarioRunResult
from cap_qa_platform.scenarios.registry import get_scenario_class


@dataclass
class RunConfig:
    url: str
    db: str
    user: str
    password: str
    protocol: str = "jsonrpc"
    roles_from: str = "db"
    roles_xml: str | None = None
    roles: list[str] | None = None
    test_login: str = TEST_USER_LOGIN
    test_password: str = TEST_USER_PASSWORD
    no_cleanup: bool = False
    strict: bool = False
    quiet: bool = False


def load_expectations(scenario_id: str) -> dict:
    for sub in ("", "scripts"):
        path = EXPECTATIONS_DIR / sub / f"{scenario_id}.json" if sub else EXPECTATIONS_DIR / f"{scenario_id}.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    return {
        "scenario": scenario_id,
        "full_access": [],
        "blocked": {},
        "notes": "Empty expectations — runs are REPORT unless strict.",
    }


def setup_environment(cfg: RunConfig) -> tuple[OdooRPCClient, RoleManager, list[dict], int | None]:
    admin = OdooRPCClient(cfg.url, cfg.db, cfg.user, cfg.password, protocol=cfg.protocol)
    admin.authenticate()
    company_id = m2o_id(admin.read("res.users", [admin.uid], ["company_id"])[0]["company_id"])
    if not company_id:
        raise RuntimeError("Admin has no company_id")

    from cap_qa_platform.paths import ROLES_DATA_XML

    xml_path = Path(cfg.roles_xml) if cfg.roles_xml else ROLES_DATA_XML
    role_defs = parse_roles_from_xml(xml_path)
    roles = resolve_roles(admin, role_defs, cfg.roles_from)
    if cfg.roles:
        wanted = set(cfg.roles)
        roles = [r for r in roles if r["name"] in wanted]
    if not roles:
        raise RuntimeError("No roles to test")

    role_manager = RoleManager(admin, cfg.test_login, cfg.test_password)
    role_manager.ensure_test_user(company_id)
    role_manager.backup_role_lines()

    fallback_partner_id = admin.create(
        "res.partner",
        {
            "name": f"CAPQA_Fallback_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "is_company": True,
            "company_id": company_id,
        },
    )
    return admin, role_manager, roles, fallback_partner_id


def run_role_matrix_scenario(
    scenario_id: str,
    cfg: RunConfig,
    roles: list[dict],
    admin: OdooRPCClient,
    role_manager: RoleManager,
    fallback_partner_id: int | None,
) -> tuple[list[dict], int]:
    expectations = load_expectations(scenario_id)
    cls = get_scenario_class(scenario_id)
    rows: list[dict] = []
    failures = 0

    for role in roles:
        role_name = role["name"]
        scenario = cls(
            no_cleanup=cfg.no_cleanup,
            fallback_partner_id=fallback_partner_id,
        )
        if hasattr(scenario, "bind_admin"):
            scenario.bind_admin(admin)
        try:
            role_manager.assign_single_role(role["id"])
            tester = role_manager.connect_as_tester(cfg.url, cfg.db, cfg.protocol)
            run_result: ScenarioRunResult = scenario.run(tester, role_name)
        except Exception as exc:
            run_result = ScenarioRunResult(
                scenario=scenario_id,
                role_name=role_name,
                success=False,
                failed_step="setup",
                error=str(exc),
            )

        classified = classify_matrix_outcome(
            role_name,
            success=run_result.success,
            failed_step=run_result.failed_step,
            error=run_result.error,
            expectations=expectations,
            strict=cfg.strict,
        )
        classified["scenario"] = scenario_id
        rows.append(classified)
        if classified["verdict"] == "FAIL":
            failures += 1

        if not cfg.no_cleanup and hasattr(scenario, "cleanup_as_admin"):
            try:
                scenario.cleanup_as_admin(admin)
            except Exception:
                pass

    return rows, failures


def run_script_matrix_scenario(
    scenario_id: str,
    cfg: RunConfig,
    roles: list[dict],
    role_manager: RoleManager,
) -> tuple[list[dict], int]:
    entry = SCRIPT_BY_ID[scenario_id]
    expectations = load_expectations(scenario_id)
    rows: list[dict] = []
    failures = 0

    for role in roles:
        role_name = role["name"]
        role_manager.assign_single_role(role["id"])
        rpc_user = cfg.user if entry.auth_user == "admin" else cfg.test_login
        rpc_password = cfg.password if entry.auth_user == "admin" else cfg.test_password
        proc = run_script(
            entry,
            url=cfg.url,
            db=cfg.db,
            user=rpc_user,
            password=rpc_password,
            protocol=cfg.protocol,
        )
        classified = classify_matrix_outcome(
            role_name,
            success=proc.success,
            failed_step=None if proc.success else "script",
            error=None if proc.success else proc.tail(),
            expectations=expectations,
            strict=cfg.strict,
        )
        classified["scenario"] = scenario_id
        rows.append(classified)
        if classified["verdict"] == "FAIL":
            failures += 1

    return rows, failures


def run_scenario(cfg: RunConfig, scenario_id: str) -> dict:
    admin, role_manager, all_roles, fallback = setup_environment(cfg)
    test_roles = all_roles
    try:
        entry = get_entry(scenario_id)
        if entry.kind == "role_matrix":
            rows, failures = run_role_matrix_scenario(
                scenario_id, cfg, test_roles, admin, role_manager, fallback
            )
        else:
            rows, failures = run_script_matrix_scenario(
                scenario_id, cfg, test_roles, role_manager
            )
    finally:
        try:
            role_manager.restore_role_lines()
        except Exception:
            pass
        if fallback and not cfg.no_cleanup:
            try:
                admin.unlink("res.partner", [fallback])
            except Exception:
                pass

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario": scenario_id,
        "db": cfg.db,
        "url": cfg.url,
        "role_count": len(rows),
        "failures": failures,
        "counts": counts,
        "roles": rows,
    }
