"""Project task form + Generate Task Test AI wizard (Odoo 19)."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from cap_qa_platform.ui.pages.odoo_form import OdooFormHelper

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page


class ProjectTaskPage:
    GENERATE_BUTTON = "Generate Task Test - AI"

    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url.rstrip("/")
        self.form = OdooFormHelper(page)

    def _wait_for_task_form(self, timeout_ms: int = 120_000) -> None:
        deadline = time.time() + (timeout_ms / 1000.0)
        while time.time() < deadline:
            if self.page.locator(
                ".o_form_view .o_field_widget[name='name'], "
                ".o_form_view .o_field_widget[name='name'] input, "
                "button[name='action_generate_tests']"
            ).count():
                return
            if self.page.locator("text=Access Error, text=Page Not Found").count():
                raise AssertionError(f"Cannot open task form at {self.page.url}")
            time.sleep(1.0)
        raise AssertionError(
            f"Task form did not load within {timeout_ms / 1000:.0f}s (url={self.page.url})."
        )

    def open_task(self, project_id: int, task_id: int) -> None:
        url = f"{self.base_url}/odoo/project/{project_id}/tasks/{task_id}"
        self.page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        self._wait_for_task_form()

    def open_task_url(self, path_or_url: str) -> None:
        if path_or_url.startswith("http"):
            url = path_or_url
        else:
            path = path_or_url if path_or_url.startswith("/") else f"/{path_or_url}"
            url = f"{self.base_url}{path}"
        self.page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        self._wait_for_task_form()

    def click_generate_task_test_ai(self) -> None:
        btn = self.page.locator(
            f"button[name='action_generate_tests'], button:has-text('{self.GENERATE_BUTTON}')"
        )
        btn.first.wait_for(state="visible", timeout=60_000)
        btn.first.click()

    def wait_ai_wizard(self, timeout_ms: int = 180_000) -> Locator:
        """Wait for AI wizard modal or raise if AI returns a warning notification."""
        deadline = time.time() + (timeout_ms / 1000.0)
        while time.time() < deadline:
            dialog = self.page.locator(".o_dialog:visible, .modal-dialog:visible")
            if dialog.count():
                rows = dialog.locator(".o_list_view tbody tr, .o_data_row")
                if rows.count() >= 1:
                    return dialog.first
            for note in self.page.locator(".o_notification:visible").all():
                text = note.inner_text().lower()
                if "unreachable" in text or "no additional task tests" in text:
                    raise AssertionError(f"Generate Task Test - AI failed: {note.inner_text()}")
            time.sleep(1.0)
        raise AssertionError(f"AI wizard did not open within {timeout_ms / 1000:.0f}s.")

    def wizard_line_count(self, dialog: Locator) -> int:
        return dialog.locator(".o_list_view tbody tr, .o_data_row").count()

    def assert_wizard_has_lines(self, dialog: Locator, minimum: int = 1) -> int:
        count = self.wizard_line_count(dialog)
        if count < minimum:
            raise AssertionError(
                f"Expected at least {minimum} suggested test(s) in wizard, found {count}."
            )
        return count

    def click_add_all(self, dialog: Locator) -> None:
        dialog.get_by_role("button", name="Add All").click(timeout=30_000)

    def wait_wizard_closed(self, timeout_ms: int = 60_000) -> None:
        self.page.locator(".o_dialog:visible, .modal-dialog:visible").wait_for(
            state="hidden",
            timeout=timeout_ms,
        )

    def open_task_tests_tab(self) -> None:
        tab = self.page.locator(
            ".nav-link:has-text('Task Tests'), button:has-text('Task Tests'), "
            "[role='tab']:has-text('Task Tests')"
        )
        tab.first.click(timeout=30_000)
        self.page.wait_for_timeout(500)

    def count_task_tests_in_tab(self) -> int:
        pane = self.page.locator(
            ".o_notebook_content:visible .o_field_widget[name='tests_ids'] "
            ".o_list_view tbody tr, "
            ".o_notebook_content:visible .o_field_widget[name='tests_ids'] .o_data_row"
        )
        if pane.count():
            return pane.count()
        return self.page.locator(
            ".o_notebook_content:visible .o_list_table tbody tr, "
            ".o_notebook_content:visible .o_data_row"
        ).count()

    def assert_task_tests_tab_has_rows(self, minimum: int = 1) -> int:
        count = self.count_task_tests_in_tab()
        if count < minimum:
            raise AssertionError(
                f"Task Tests tab shows {count} row(s), expected at least {minimum}."
            )
        return count
