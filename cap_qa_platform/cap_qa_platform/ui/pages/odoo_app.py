"""Odoo backend shell navigation helpers."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page


class OdooAppShell:
    def __init__(self, page: Page):
        self.page = page

    def wait_for_home(self, timeout: int = 120_000) -> None:
        """Wait for Odoo 19 backend home / app switcher."""
        self.page.wait_for_url("**/odoo**", timeout=timeout, wait_until="domcontentloaded")
        self.page.get_by_text("Discuss", exact=True).first.wait_for(
            state="visible", timeout=timeout
        )

    def open_app(self, app_name: str) -> None:
        """Open app from Odoo 19 home grid."""
        self.wait_for_home()
        self.page.get_by_text(app_name, exact=True).first.click(timeout=30_000)
        self.page.wait_for_load_state("domcontentloaded", timeout=120_000)

    def assert_menu_accessible(self, app_name: str) -> None:
        from playwright.sync_api import expect

        self.wait_for_home()
        expect(self.page.get_by_text(app_name, exact=True).first).to_be_visible(
            timeout=60_000
        )
