"""Unified matrix runner — any registered scenario × all roles."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from test_automation.catalog import SCRIPT_BY_ID
from test_automation.matrix_common import classify_matrix_outcome
from test_automation.paths import EXPECTATIONS, EXPECTATIONS_SCRIPTS
from test_automation.rpc.client import OdooRPCClient, m2o_id
from test_automation.rpc.errors import is_access_error
from test_automation.rpc.role_manager import RoleManager
from test_automation.scenarios.registry import get_scenario_class, is_script_scenario
from test_automation.scenarios.script_scenario import MatrixRunContext, ScriptSubprocessScenario
from test_automation.script_matrix.config import get_script_matrix_config


@dataclass
class MatrixArgs:
    url: str
    db: str
    user: str
    password: str
    protocol: str
    roles_from: str
    roles_xml: str
    roles: list[str] | None
    test_login: str
    test_password: str
    no_cleanup: bool
    strict: bool
    quiet: bool
    no_project_pm: bool = False
    script_extra: tuple[str, ...] = ()


def load_expectations(scenario_id: str, path: Path | None = None) -> dict:
    if path and path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    if is_script_scenario(scenario_id):
        file_path = EXPECTATIONS_SCRIPTS / f"{scenario_id}.json"
        if file_path.is_file():
            return json.loads(file_path.read_text(encoding="utf-8"))
        return {
            "scenario": scenario_id,
            "full_access": [],
            "blocked": {},
            "notes": "Auto-generated empty expectations — run matrix and update full_access/blocked.",
        }
    file_path = EXPECTATIONS / f"{scenario_id}.json"
    if not file_path.is_file():
        raise FileNotFoundError(f"Expectations file not found: {file_path}")
    return json.loads(file_path.read_text(encoding="utf-8"))


def classify_role_scenario_result(
    role_name: str,
    run_result,
    expectations: dict,
    strict: bool,
) -> dict:
    """Verdict for native RPC scenarios (step-level blocked expectations)."""
    full_access = set(expectations.get("full_access") or [])
    blocked = expectations.get("blocked") or {}
    blocked_spec = blocked.get(role_name)

    verdict = "REPORT"
    detail = ""

    if role_name in full_access:
        if run_result.success:
            verdict = "PASS"
            detail = "Full flow completed"
            q_expected = expectations.get("quality_log_count")
            if q_expected is not None and run_result.quality_log_count != q_expected:
                verdict = "FAIL"
                detail = (
                    f"quality.issue.log count={run_result.quality_log_count}, "
                    f"expected {q_expected}"
                )
        else:
            verdict = "FAIL"
            detail = f"Expected full access; failed at {run_result.failed_step}: {run_result.error}"

    elif blocked_spec:
        expected_step = blocked_spec.get("at")
        if not run_result.success and run_result.failed_step == expected_step:
            if is_access_error(Exception(run_result.error or "")):
                verdict = "BLOCKED_OK"
                detail = f"Blocked at {expected_step} as expected"
            else:
                verdict = "FAIL"
                detail = f"Blocked at {expected_step} but not AccessError: {run_result.error}"
        elif run_result.success:
            verdict = "FAIL"
            detail = "Expected block but full flow succeeded"
        else:
            verdict = "FAIL"
            detail = (
                f"Expected block at {expected_step}, "
                f"got {run_result.failed_step}: {run_result.error}"
            )
    else:
        if run_result.success:
            detail = "Completed (not in full_access list — review expectations)"
        else:
            detail = f"Failed at {run_result.failed_step}: {run_result.error}"
        if strict and not run_result.success:
            verdict = "FAIL"
        elif strict and run_result.success and role_name not in full_access:
            verdict = "REPORT"

    row = {
        "role": role_name,
        "verdict": verdict,
        "detail": detail,
        "success": run_result.success,
        "failed_step": run_result.failed_step,
        "error": run_result.error,
        "records": run_result.records,
        "quality_log_count": run_result.quality_log_count,
        "steps": [
            {"step": s.step, "ok": s.ok, "error": s.error} for s in run_result.steps
        ],
    }
    return row


def _instantiate_scenario(
    scenario_cls: type,
    args: MatrixArgs,
    fallback_partner_id: int | None,
):
    if issubclass(scenario_cls, ScriptSubprocessScenario):
        return scenario_cls(no_cleanup=args.no_cleanup)
    return scenario_cls(
        no_cleanup=args.no_cleanup,
        assign_project_pm=not args.no_project_pm,
        fallback_partner_id=fallback_partner_id,
    )


def run_scenario_matrix(
    scenario_id: str,
    args: MatrixArgs,
    *,
    roles: list[dict],
    admin: OdooRPCClient,
    role_manager: RoleManager,
    fallback_partner_id: int | None = None,
    expectations: dict | None = None,
) -> tuple[list[dict], int]:
    """Run one scenario for every role. Returns (role_rows, failure_count)."""
    scenario_cls = get_scenario_class(scenario_id)
    expectations = expectations or load_expectations(scenario_id)
    script_mode = is_script_scenario(scenario_id)
    matrix_cfg = get_script_matrix_config(scenario_id) if script_mode else None

    role_results: list[dict] = []
    failures = 0

    for role in roles:
        role_name = role["name"]
        scenario = _instantiate_scenario(scenario_cls, args, fallback_partner_id)

        if script_mode:
            ctx = MatrixRunContext(
                url=args.url,
                db=args.db,
                protocol=args.protocol,
                admin_user=args.user,
                admin_password=args.password,
                test_login=args.test_login,
                test_password=args.test_password,
                role=role,
                quiet=args.quiet,
                script_extra=args.script_extra,
            )
            scenario.set_matrix_context(ctx)
            if matrix_cfg and matrix_cfg.assign_role:
                role_manager.assign_single_role(role["id"])
        else:
            if hasattr(scenario, "bind_admin"):
                scenario.bind_admin(admin)
            try:
                role_manager.assign_single_role(role["id"])
                tester = role_manager.connect_as_tester(args.url, args.db, args.protocol)
            except Exception as exc:
                from test_automation.scenarios.base import ScenarioRunResult

                run_result = ScenarioRunResult(
                    scenario=scenario_id,
                    role_name=role_name,
                    success=False,
                    failed_step="setup",
                    error=str(exc),
                )
                classified = classify_role_scenario_result(
                    role_name, run_result, expectations, args.strict
                )
                classified["scenario"] = scenario_id
                role_results.append(classified)
                if classified["verdict"] == "FAIL":
                    failures += 1
                continue

        try:
            if script_mode:
                run_result = scenario.run(None, role_name)
            else:
                run_result = scenario.run(tester, role_name)
        except Exception as exc:
            from test_automation.scenarios.base import ScenarioRunResult

            run_result = ScenarioRunResult(
                scenario=scenario_id,
                role_name=role_name,
                success=False,
                failed_step="setup",
                error=str(exc),
            )

        if script_mode:
            classified = classify_matrix_outcome(
                role_name,
                success=run_result.success,
                failed_step=run_result.failed_step,
                error=run_result.error,
                expectations=expectations,
                strict=args.strict,
            )
        else:
            classified = classify_role_scenario_result(
                role_name, run_result, expectations, args.strict
            )

        classified["scenario"] = scenario_id
        role_results.append(classified)
        if classified["verdict"] == "FAIL":
            failures += 1

        if not args.no_cleanup and not script_mode:
            scenario.cleanup_as_admin(admin)

    return role_results, failures


def run_scenarios_matrix(
    scenario_ids: list[str],
    args: MatrixArgs,
    *,
    roles: list[dict],
    admin: OdooRPCClient,
    role_manager: RoleManager,
    fallback_partner_id: int | None = None,
) -> dict[str, Any]:
    """Run multiple scenarios × roles; return combined report dict."""
    all_results: list[dict] = []
    total_failures = 0

    for scenario_id in scenario_ids:
        rows, failures = run_scenario_matrix(
            scenario_id,
            args,
            roles=roles,
            admin=admin,
            role_manager=role_manager,
            fallback_partner_id=fallback_partner_id,
        )
        all_results.extend(rows)
        total_failures += failures

    counts: dict[str, int] = {}
    for row in all_results:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "type": "matrix",
        "scenarios": scenario_ids,
        "role_count": len(roles),
        "total_runs": len(all_results),
        "failures": total_failures,
        "counts": counts,
        "db": args.db,
        "url": args.url,
        "results": all_results,
    }


def setup_matrix_environment(
    args: MatrixArgs,
    parse_roles_from_xml,
    resolve_roles,
) -> tuple[OdooRPCClient, RoleManager, list[dict], int | None]:
    """Authenticate admin, resolve roles, ensure test user. Returns fallback partner id."""
    admin = OdooRPCClient(
        args.url, args.db, args.user, args.password, protocol=args.protocol
    )
    admin.authenticate()
    admin_user = admin.read("res.users", [admin.uid], ["company_id"])[0]
    company_id = m2o_id(admin_user.get("company_id"))
    if not company_id:
        raise RuntimeError("Admin has no company_id")

    role_defs = parse_roles_from_xml(Path(args.roles_xml))
    roles = resolve_roles(admin, role_defs, args.roles_from)
    if args.roles:
        wanted = {n.lower() for n in args.roles}
        roles = [r for r in roles if r["name"].lower() in wanted]
    if not roles:
        raise RuntimeError("No roles found")

    role_manager = RoleManager(admin, args.test_login, args.test_password)
    role_manager.ensure_test_user(company_id)
    role_manager.backup_role_lines()

    fallback_partner_id = admin.create(
        "res.partner",
        {
            "name": f"FeatureMatrix_Fallback_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "company_type": "company",
            "is_company": True,
            "company_id": company_id,
        },
    )
    return admin, role_manager, roles, fallback_partner_id


MISTRAL_KEY_PARAM = "connect_mistral_ai.mistral_key"


def setup_global_mistral_key(admin: OdooRPCClient, key: str) -> None:
    """Set Mistral API key once server-side (admin). Role users never need Settings access."""
    if not key:
        return
    admin.execute_kw("ir.config_parameter", "set_param", [MISTRAL_KEY_PARAM, key])
