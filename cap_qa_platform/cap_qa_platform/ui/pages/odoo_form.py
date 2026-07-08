"""Odoo 19 form field helpers for Playwright."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page


class OdooFormHelper:
    def __init__(self, page: Page):
        self.page = page

    def select_many2one(self, field_name: str, search_text: str, timeout: int = 30_000) -> None:
        inp = self.page.locator(f".o_field_widget[name='{field_name}'] input").first
        inp.click()
        inp.fill("")
        inp.fill(search_text)
        item = self.page.locator(".o-autocomplete--dropdown-item").filter(
            has_text=search_text
        ).first
        item.wait_for(state="visible", timeout=timeout)
        item.click()

    def select_many2one_partial(self, field_name: str, search_text: str, timeout: int = 30_000) -> None:
        """Select first autocomplete match containing search_text."""
        inp = self.page.locator(f".o_field_widget[name='{field_name}'] input").first
        inp.click()
        inp.fill("")
        inp.fill(search_text)
        item = self.page.locator(".o-autocomplete--dropdown-item").filter(
            has_text=search_text
        ).first
        item.wait_for(state="visible", timeout=timeout)
        item.click()

    def select_many2one_in(self, container, field_name: str, search_text: str) -> None:
        widget = container.locator(f".o_field_widget[name='{field_name}']")
        widget.click()
        inp = widget.locator("input")
        inp.wait_for(state="visible", timeout=10_000)
        inp.fill("")
        snippet = search_text if len(search_text) <= 25 else search_text[:25]
        inp.fill(snippet)
        self.page.locator(".o-autocomplete--dropdown-item").filter(
            has_text=snippet
        ).first.click(timeout=30_000)

    def click_button(self, name: str, timeout: int = 30_000) -> None:
        self.page.get_by_role("button", name=name).first.click(timeout=timeout)

    def click_statusbar_button(self, name: str, timeout: int = 30_000) -> None:
        btn = self.page.locator(".o_statusbar_buttons button, header button").filter(has_text=name)
        btn.first.click(timeout=timeout)

    def confirm_modal(self, button_text: str = "Submit") -> None:
        dialog = self.page.locator(".modal-dialog:visible, .o_dialog:visible")
        if dialog.count():
            dialog.get_by_role("button", name=button_text).click(timeout=15_000)

    def dismiss_modals(self, prefer_button: str | None = None) -> None:
        for _ in range(5):
            dialog = self.page.locator(".modal-dialog:visible, .o_dialog:visible")
            if not dialog.count():
                return
            if prefer_button:
                btn = dialog.get_by_role("button", name=prefer_button)
                if btn.count():
                    btn.first.click(timeout=10_000)
                    self.page.wait_for_timeout(500)
                    continue
            for label in ("Ok", "OK", "Close", "Discard", "Continue", "Confirm", "Submit"):
                btn = dialog.get_by_role("button", name=label)
                if btn.count():
                    btn.first.click(timeout=10_000)
                    self.page.wait_for_timeout(500)
                    break
            else:
                self.page.keyboard.press("Escape")
                self.page.wait_for_timeout(500)
