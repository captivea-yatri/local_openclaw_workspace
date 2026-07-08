"""Hybrid UI+RPC flow for SO cancel scenario."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from cap_qa_platform.backend.runner import RunConfig, run_scenario
from cap_qa_platform.rpc.client import OdooRPCClient, m2o_id
from cap_qa_platform.rpc.role_manager import TEST_USER_LOGIN, TEST_USER_PASSWORD
from cap_qa_platform.rpc.tester_employee import ensure_tester_employee
from cap_qa_platform.ui.config import headless, odoo_db, odoo_url
from cap_qa_platform.ui.data.so_cancel_data import prepare_so_cancel_data
from cap_qa_platform.ui.pages.login import LoginPage
from cap_qa_platform.ui.pages.sale_order import SaleOrderPage
from cap_qa_platform.ui.session import prepare_ui_session

UI_STEPS = (
    "ui_login",
    "create_sale_order",
    "action_confirm",
    "assert_customer_status",
    "link_so_project",
    "ensure_tester_employee",
    "assign_project_user",
    "action_cancel",
    "assert_old_customer_status",
    "assert_quality_logs",
)


@dataclass
class UiStepResult:
    step: str
    ok: bool
    error: str | None = None


@dataclass
class UiFlowResult:
    ok: bool
    detail: str
    steps: list[UiStepResult] = field(default_factory=list)
    backend_report: dict | None = None
    records: dict | None = None


def _test_credentials() -> tuple[str, str]:
    return (
        os.environ.get("CAP_QA_TEST_LOGIN", TEST_USER_LOGIN),
        os.environ.get("CAP_QA_TEST_PASSWORD", TEST_USER_PASSWORD),
    )


def _wait_for_partner_status(
    rpc: OdooRPCClient,
    partner_id: int,
    so_id: int,
    expected: str,
    timeout: float = 60.0,
) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        partner_status = rpc.read("res.partner", [partner_id], ["status"])[0].get("status")
        so_state = rpc.read("sale.order", [so_id], ["state"])[0].get("state")
        if partner_status == expected and so_state == "sale":
            return
        if expected == "old_customer" and partner_status == expected:
            return
        time.sleep(1.0)
    partner_status = rpc.read("res.partner", [partner_id], ["status"])[0].get("status")
    raise AssertionError(
        f"Partner status '{partner_status}', expected '{expected}' (timeout {timeout}s)."
    )


def _assert_partner_status(rpc: OdooRPCClient, partner_id: int, expected: str) -> None:
    actual = rpc.read("res.partner", [partner_id], ["status"])[0].get("status")
    if actual != expected:
        raise AssertionError(f"Partner status '{actual}', expected '{expected}'.")


def _resolve_project_id(rpc: OdooRPCClient, partner_id: int) -> int:
    projects = rpc.search(
        "project.project",
        [("partner_id", "=", partner_id)],
        limit=1,
        order="id desc",
    )
    if not projects:
        raise AssertionError("No project found for partner after link_so_project.")
    return projects[0]


def _run_step(steps: list[UiStepResult], step: str, fn) -> None:
    try:
        fn()
        steps.append(UiStepResult(step=step, ok=True))
    except Exception as exc:
        steps.append(UiStepResult(step=step, ok=False, error=str(exc)))
        raise


def run_so_cancel_ui_smoke(
    role: str = "President", *, skip_backend: bool = True
) -> UiFlowResult:
    """Full UI flow mirroring backend so_cancel_old_customer scenario."""
    test_login, test_password = _test_credentials()
    cfg = RunConfig(
        url=odoo_url(),
        db=odoo_db(),
        user=os.environ.get("ODOO_USER", "admin"),
        password=os.environ.get("ODOO_PASSWORD", "admin"),
        roles=[role],
        test_login=test_login,
        test_password=test_password,
    )
    steps: list[UiStepResult] = []
    backend: dict | None = None
    role_manager = None
    scenario_base = None
    admin = None
    data = None
    project_id: int | None = None
    log_count = 0

    try:
        admin, role_manager = prepare_ui_session(cfg, role)
        if not skip_backend:
            backend = run_scenario(cfg, "so_cancel_old_customer")

        tester = OdooRPCClient(cfg.url, cfg.db, cfg.test_login, cfg.test_password)
        tester.authenticate()
        data, scenario_base = prepare_so_cancel_data(tester, admin)

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            steps.append(UiStepResult("playwright_import", False, str(exc)))
            return UiFlowResult(False, f"Playwright not installed: {exc}", steps, backend)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless())
            page = browser.new_page()
            so_page = SaleOrderPage(page)
            try:
                def do_login() -> None:
                    login = LoginPage(page, odoo_url())
                    login.login(odoo_db(), test_login, test_password)
                    if not login.is_logged_in():
                        raise RuntimeError(f"expected /odoo, got {page.url}")

                _run_step(steps, "ui_login", do_login)
                _run_step(
                    steps,
                    "create_sale_order",
                    lambda: (
                        so_page.open_sales_new_quotation(),
                        so_page.fill_assistance_order(data),
                    ),
                )
                _run_step(steps, "action_confirm", so_page.confirm_order)
                so_id = so_page.current_record_id()
                scenario_base._track("sale.order", so_id)
                _run_step(
                    steps,
                    "assert_customer_status",
                    lambda: _wait_for_partner_status(
                        tester, data.partner_id, so_id, "customer"
                    ),
                )

                def link_project() -> None:
                    nonlocal project_id
                    wiz_id = tester.create("link.so.project.wizard", {"operation": "create"})
                    tester.call(
                        "link.so.project.wizard",
                        "link_so_project",
                        [wiz_id],
                        context={
                            "active_model": "sale.order",
                            "active_id": so_id,
                            "active_ids": [so_id],
                        },
                    )
                    project_id = _resolve_project_id(tester, data.partner_id)
                    scenario_base._track("project.project", project_id)

                _run_step(steps, "link_so_project", link_project)

                company_id = m2o_id(
                    admin.read("res.users", [tester.uid], ["company_id"])[0]["company_id"]
                )

                def ensure_employee() -> None:
                    ensure_tester_employee(
                        admin,
                        tester.uid,
                        company_id,
                        track=scenario_base._track if not scenario_base.no_cleanup else None,
                    )

                _run_step(steps, "ensure_tester_employee", ensure_employee)

                def assign_pm() -> None:
                    nonlocal project_id
                    project_id = _resolve_project_id(tester, data.partner_id)
                    tester.write("project.project", [project_id], {"user_id": tester.uid})

                _run_step(steps, "assign_project_user", assign_pm)
                _run_step(steps, "action_cancel", so_page.cancel_order)
                _run_step(
                    steps,
                    "assert_old_customer_status",
                    lambda: _wait_for_partner_status(
                        tester, data.partner_id, so_id, "old_customer"
                    ),
                )

                def count_logs() -> None:
                    nonlocal log_count
                    log_count = tester.search_count(
                        "quality.issue.log", [("project_id", "=", project_id)]
                    )
                    if log_count < 1:
                        raise AssertionError(
                            f"Expected at least 1 quality.issue.log for project {project_id}, "
                            f"found {log_count}."
                        )

                _run_step(steps, "assert_quality_logs", count_logs)
            except Exception:
                browser.close()
                failed = next((s for s in reversed(steps) if not s.ok), steps[-1] if steps else None)
                msg = f"UI failed at {failed.step}: {failed.error}" if failed else "UI failed"
                return UiFlowResult(False, msg, steps, backend)
            browser.close()

        records = {
            "partner_id": data.partner_id,
            "sale_order_id": so_id,
            "project_id": project_id,
            "quality_log_count": log_count,
        }
        return UiFlowResult(
            True,
            f"All {len(steps)} UI steps passed",
            steps,
            backend,
            records,
        )
    finally:
        if scenario_base is not None and admin is not None:
            try:
                scenario_base.cleanup_as_admin(admin)
            except Exception:
                pass
        if role_manager is not None:
            try:
                role_manager.restore_role_lines()
            except Exception:
                pass
