"""UI flow: Task Need & Solutions via AI Assistant on project.task."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from cap_qa_platform.backend.runner import RunConfig
from cap_qa_platform.rpc.client import OdooRPCClient
from cap_qa_platform.rpc.role_manager import TEST_USER_LOGIN, TEST_USER_PASSWORD
from cap_qa_platform.ui.config import headless, odoo_db, odoo_url
from cap_qa_platform.ui.data.task_need_solutions_ai_data import (
    build_user_message,
    load_task_need_solutions_data,
    read_description_plain,
)
from cap_qa_platform.ui.pages.ai_assistant import AiAssistantPanel
from cap_qa_platform.ui.pages.login import LoginPage
from cap_qa_platform.ui.pages.project_task import ProjectTaskPage
from cap_qa_platform.ui.session import prepare_ui_session


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
    records: dict | None = None


def _test_credentials() -> tuple[str, str]:
    return (
        os.environ.get("CAP_QA_TEST_LOGIN", TEST_USER_LOGIN),
        os.environ.get("CAP_QA_TEST_PASSWORD", TEST_USER_PASSWORD),
    )


def _existing_task_target() -> tuple[int | None, str | None]:
    return (
        int(os.environ["CAP_QA_TASK_ID"]) if os.environ.get("CAP_QA_TASK_ID") else None,
        os.environ.get("CAP_QA_TASK_URL"),
    )


def _run_step(steps: list[UiStepResult], step: str, fn) -> None:
    try:
        fn()
        steps.append(UiStepResult(step=step, ok=True))
    except Exception as exc:
        steps.append(UiStepResult(step=step, ok=False, error=str(exc)))
        raise


def _wait_description_changed(
    admin: OdooRPCClient,
    task_id: int,
    before: str,
    timeout: float = 90.0,
) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        after = read_description_plain(admin, task_id)
        if after and after != before and len(after) > len(before):
            lowered = after.lower()
            if "need" in lowered or "solution" in lowered:
                return after
        time.sleep(2.0)
    after = read_description_plain(admin, task_id)
    raise AssertionError(
        "Task description was not updated with Need/Solution content after 'Let's do it!' "
        f"(before_len={len(before)}, after_len={len(after)})."
    )


def run_task_need_solutions_ai_ui_smoke(role: str = "President", **kwargs) -> UiFlowResult:
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
    role_manager = None
    admin = None
    data = None
    description_before = ""
    description_after = ""
    assistant_reply = ""

    try:
        admin, role_manager = prepare_ui_session(cfg, role)
        task_id, task_url = _existing_task_target()
        if not task_id and not task_url:
            raise ValueError(
                "task_need_solutions_ai UI requires --task-url or --task-id "
                "(existing project.task with AI Assistant)."
            )

        data = load_task_need_solutions_data(admin, task_id=task_id, task_url=task_url)
        description_before = read_description_plain(admin, data.task_id)

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            steps.append(UiStepResult("playwright_import", False, str(exc)))
            return UiFlowResult(False, f"Playwright not installed: {exc}", steps)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless())
            page = browser.new_page()
            task_page = ProjectTaskPage(page, odoo_url())
            ai = AiAssistantPanel(page)
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
                _run_step(steps, "open_ask_ai", ai.open_from_task_form)

                def submit_transcript_and_prompt() -> None:
                    ai.send_message(build_user_message(data.transcript, data.prompt))

                _run_step(steps, "submit_transcript_and_prompt", submit_transcript_and_prompt)

                def wait_reply() -> None:
                    nonlocal assistant_reply
                    assistant_reply = ai.wait_for_assistant_reply()

                _run_step(steps, "review_generated_need_solution", wait_reply)
                _run_step(steps, "click_lets_do_it", ai.click_lets_do_it)

                def reopen_and_verify() -> None:
                    nonlocal description_after
                    if data.task_url:
                        task_page.open_task_url(data.task_url)
                    else:
                        task_page.open_task(data.project_id, data.task_id)
                    description_after = _wait_description_changed(
                        admin, data.task_id, description_before
                    )

                _run_step(steps, "verify_task_description_updated", reopen_and_verify)
            except Exception:
                browser.close()
                failed = next((s for s in reversed(steps) if not s.ok), steps[-1] if steps else None)
                msg = f"UI failed at {failed.step}: {failed.error}" if failed else "UI failed"
                return UiFlowResult(False, msg, steps)
            browser.close()

        records = {
            "project_id": data.project_id,
            "task_id": data.task_id,
            "task_name": data.task_name,
            "task_url": data.task_url,
            "description_before_len": len(description_before),
            "description_after_len": len(description_after),
            "assistant_reply_preview": assistant_reply[:240],
        }
        return UiFlowResult(True, f"All {len(steps)} UI steps passed", steps, records)
    finally:
        if role_manager is not None:
            try:
                role_manager.restore_role_lines()
            except Exception:
                pass
