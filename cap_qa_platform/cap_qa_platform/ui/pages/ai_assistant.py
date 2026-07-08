"""Odoo 19 AI Assistant chat panel (connect_mistral_ai / mail ai_chat)."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page


class AiAssistantPanel:
    ASK_AI_LABEL = "Ask AI"
    CONFIRM_LABEL = "Let's do it!"

    def __init__(self, page: Page):
        self.page = page

    def open_from_task_form(self, timeout_ms: int = 60_000) -> None:
        selectors = (
            f"button:has-text('{self.ASK_AI_LABEL}')",
            f"[aria-label='{self.ASK_AI_LABEL}']",
            f"[title='{self.ASK_AI_LABEL}']",
            "button.o_form_ai_button",
            "[aria-label*='Ask AI']",
            "[title*='Ask AI']",
            "button:has-text('AI Assistant')",
            "[aria-label*='AI Assistant']",
        )
        deadline = time.time() + (timeout_ms / 1000.0)
        last_error = "Ask AI button not found on task form."
        while time.time() < deadline:
            for selector in selectors:
                btn = self.page.locator(selector)
                for i in range(btn.count()):
                    candidate = btn.nth(i)
                    try:
                        if not candidate.is_visible():
                            continue
                        candidate.click(timeout=10_000)
                        self._wait_for_chat_open()
                        return
                    except Exception as exc:
                        last_error = str(exc)
            time.sleep(0.5)
        raise AssertionError(last_error)

    def _wait_for_chat_open(self, timeout_ms: int = 120_000) -> None:
        deadline = time.time() + (timeout_ms / 1000.0)
        while time.time() < deadline:
            composer = self.page.locator(
                ".o-mail-Composer-input textarea, "
                ".o-mail-Composer-input [contenteditable='true']"
            )
            chat_window = self.page.locator(".o-mail-ChatWindow")
            for i in range(composer.count()):
                if composer.nth(i).is_visible():
                    return
            for i in range(chat_window.count()):
                if chat_window.nth(i).is_visible():
                    return
            ai_panel = self.page.locator(
                ".o-ai-chat-container, .o-ai-chat, [class*='AiChatContainer']"
            )
            for i in range(ai_panel.count()):
                if ai_panel.nth(i).is_visible():
                    return
            time.sleep(0.5)
        raise AssertionError(
            f"'{self.ASK_AI_LABEL}' chat did not open within {timeout_ms / 1000:.0f}s."
        )

    def _composer(self):
        return self.page.locator(
            ".o-mail-Composer-input textarea:visible, "
            ".o-mail-Composer-input [contenteditable='true']:visible, "
            ".o-mail-ChatWindow textarea:visible, "
            ".o-ai-chat textarea:visible, "
            ".o-ai-chat [contenteditable='true']:visible"
        ).last

    def send_message(self, text: str) -> None:
        composer = self._composer()
        composer.wait_for(state="visible", timeout=30_000)
        composer.click()
        composer.fill(text)
        sent = False
        for selector in (
            ".o-mail-Composer-send:visible",
            "button[aria-label='Send']:visible",
            "button:has-text('Send'):visible",
        ):
            btn = self.page.locator(selector)
            if btn.count():
                btn.last.click()
                sent = True
                break
        if not sent:
            composer.press("Enter")
        self.page.wait_for_timeout(1000)

    def wait_for_assistant_reply(self, timeout_ms: int = 180_000) -> str:
        deadline = time.time() + (timeout_ms / 1000.0)
        last_body = ""
        while time.time() < deadline:
            bodies = self.page.locator(
                ".o-mail-Message:not(.o-self) .o-mail-Message-body, "
                ".o-mail-Message-content, "
                ".o-mail-Message-text, "
                ".o-ai-chat .o-mail-Message-body"
            )
            if bodies.count():
                last_body = bodies.last.inner_text().strip()
                if len(last_body) >= 40:
                    return last_body
            time.sleep(1.0)
        raise AssertionError(
            f"AI did not return a substantive reply within {timeout_ms / 1000:.0f}s."
        )

    def click_lets_do_it(self, timeout_ms: int = 60_000) -> None:
        btn = self.page.get_by_role("button", name=self.CONFIRM_LABEL)
        if btn.count() == 0:
            btn = self.page.get_by_text(self.CONFIRM_LABEL, exact=True)
        btn.first.wait_for(state="visible", timeout=timeout_ms)
        btn.first.click()
        self.page.wait_for_load_state("domcontentloaded", timeout=120_000)
