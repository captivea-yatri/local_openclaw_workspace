"""Odoo web login page object."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page


class LoginPage:
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url.rstrip("/")

    def goto(self) -> None:
        self.page.goto(f"{self.base_url}/web/login", wait_until="domcontentloaded")

    def login(self, db: str, login: str, password: str) -> None:
        self.goto()
        db_input = self.page.locator("input[name='db'], select[name='db']")
        if db_input.count():
            tag = db_input.first.evaluate("el => el.tagName.toLowerCase()")
            if tag == "select":
                db_input.first.select_option(value=db)
            else:
                db_input.first.fill(db)
        login_input = self.page.locator("input[name='login']")
        login_input.wait_for(state="visible", timeout=60_000)
        login_input.fill(login)
        self.page.fill("input[name='password']", password)
        submit = self.page.locator(
            "button[type='submit'], button:has-text('Log in'), button:has-text('Sign in')"
        )
        submit.first.click()
        self.page.wait_for_url("**/odoo**", timeout=120_000, wait_until="domcontentloaded")

    def is_logged_in(self) -> bool:
        return "/odoo" in self.page.url
