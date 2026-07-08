"""Hybrid UI+RPC flow for Generate Task Test - AI."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from cap_qa_platform.backend.runner import RunConfig, run_scenario
from cap_qa_platform.rpc.client import OdooRPCClient
from cap_qa_platform.rpc.role_manager import TEST_USER_LOGIN, TEST_USER_PASSWORD
from cap_qa_platform.ui.config import headless, odoo_db, odoo_url
from cap_qa_platform.ui.data.generate_task_test_ai_data import (
    load_existing_task_data,
    prepare_generate_task_test_ai_data,
)
from cap_qa_platform.ui.pages.login import LoginPage
from cap_qa_platform.ui.pages.project_task import ProjectTaskPage
from cap_qa_platform.ui.session import prepare_ui_session

UI_STEPS = (
    "ui_login",
    "open_task",
    "click_generate_task_test_ai",
    "review_wizard_lines",
    "click_add_all",
    "open_task_tests_tab",
    "assert_task_tests_in_ui",
    "assert_task_tests_rpc",
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


def _no_cleanup() -> bool:
    return os.environ.get("CAP_QA_NO_CLEANUP", "0") == "1"


def _existing_task_target() -> tuple[int | None, str | None]:
    task_url = os.environ.get("CAP_QA_TASK_URL")
    task_id_raw = os.environ.get("CAP_QA_TASK_ID")
    task_id = int(task_id_raw) if task_id_raw else None
    return task_id, task_url


def _run_step(steps: list[UiStepResult], step: str, fn) -> None:
    try:
        fn()
        steps.append(UiStepResult(step=step, ok=True))
    except Exception as exc:
        steps.append(UiStepResult(step=step, ok=False, error=str(exc)))
        raise


def _wait_for_test_count(
    rpc: OdooRPCClient,
    task_id: int,
    minimum: int,
    timeout: float = 30.0,
) -> int:
    deadline = time.time() + timeout
    while time.time() < deadline:
        count = rpc.search_count("test.test", [("task_id", "=", task_id)])
        if count >= minimum:
            return count
        time.sleep(1.0)
    count = rpc.search_count("test.test", [("task_id", "=", task_id)])
    raise AssertionError(
        f"Expected at least {minimum} test.test record(s) for task {task_id}, found {count}."
    )


def run_generate_task_test_ai_ui_smoke(
    role: str = "President", *, skip_backend: bool = True
) -> UiFlowResult:
    test_login, test_password = _test_credentials()
    cfg = RunConfig(
        url=odoo_url(),
        db=odoo_db(),
        user=os.environ.get("ODOO_USER", "admin"),
        password=os.environ.get("ODOO_PASSWORD", "admin"),
        roles=[role],
        test_login=test_login,
        test_password=test_password,
        no_cleanup=_no_cleanup(),
    )
    steps: list[UiStepResult] = []
    backend: dict | None = None
    role_manager = None
    scenario = None
    admin = None
    data = None
    tests_before = 0
    tests_after = 0
    wizard_lines = 0

    try:
        admin, role_manager = prepare_ui_session(cfg, role)
        if not skip_backend:
            backend = run_scenario(cfg, "generate_task_test_ai")

        tester = OdooRPCClient(cfg.url, cfg.db, cfg.test_login, cfg.test_password)
        tester.authenticate()
        existing_task_id, existing_task_url = _existing_task_target()
        if existing_task_id or existing_task_url:
            data = load_existing_task_data(
                admin,
                task_id=existing_task_id,
                task_url=existing_task_url,
            )
            scenario = None
        else:
            data, scenario = prepare_generate_task_test_ai_data(
                tester, admin, no_cleanup=cfg.no_cleanup
            )
        tests_before = tester.search_count("test.test", [("task_id", "=", data.task_id)])

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            steps.append(UiStepResult("playwright_import", False, str(exc)))
            return UiFlowResult(False, f"Playwright not installed: {exc}", steps, backend)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless())
            page = browser.new_page()
            task_page = ProjectTaskPage(page, odoo_url())
            dialog = None
            try:
                def do_login() -> None:
                    login = LoginPage(page, odoo_url())
                    login.login(odoo_db(), test_login, test_password)
                    if not login.is_logged_in():
                        raise RuntimeError(f"expected /odoo, got {page.url}")

                _run_step(steps, "ui_login", do_login)
                def open_task() -> None:
                    if data.task_url:
                        task_page.open_task_url(data.task_url)
                    else:
                        task_page.open_task(data.project_id, data.task_id)

                _run_step(steps, "open_task", open_task)
                _run_step(steps, "click_generate_task_test_ai", task_page.click_generate_task_test_ai)

                def review_wizard() -> None:
                    nonlocal dialog, wizard_lines
                    dialog = task_page.wait_ai_wizard()
                    wizard_lines = task_page.assert_wizard_has_lines(dialog)

                _run_step(steps, "review_wizard_lines", review_wizard)

                def add_all() -> None:
                    assert dialog is not None
                    task_page.click_add_all(dialog)
                    task_page.wait_wizard_closed()

                _run_step(steps, "click_add_all", add_all)
                _run_step(steps, "open_task_tests_tab", task_page.open_task_tests_tab)
                _run_step(
                    steps,
                    "assert_task_tests_in_ui",
                    lambda: task_page.assert_task_tests_tab_has_rows(
                        minimum=max(tests_before + 1, 1)
                    ),
                )
                _run_step(
                    steps,
                    "assert_task_tests_rpc",
                    lambda: _wait_for_test_count(
                        tester, data.task_id, tests_before + max(wizard_lines, 1)
                    ),
                )
                tests_after = tester.search_count("test.test", [("task_id", "=", data.task_id)])
            except Exception:
                browser.close()
                failed = next((s for s in reversed(steps) if not s.ok), steps[-1] if steps else None)
                msg = f"UI failed at {failed.step}: {failed.error}" if failed else "UI failed"
                return UiFlowResult(False, msg, steps, backend)
            browser.close()

        records = {
            "project_id": data.project_id,
            "task_id": data.task_id,
            "task_name": data.task_name,
            "task_url": data.task_url,
            "tests_before": tests_before,
            "tests_after": tests_after,
            "wizard_lines": wizard_lines,
        }
        return UiFlowResult(
            True,
            f"All {len(steps)} UI steps passed",
            steps,
            backend,
            records,
        )
    finally:
        if scenario is not None and admin is not None and not _no_cleanup():
            try:
                scenario.cleanup_as_admin(admin)
            except Exception:
                pass
        if role_manager is not None:
            try:
                role_manager.restore_role_lines()
            except Exception:
                pass
