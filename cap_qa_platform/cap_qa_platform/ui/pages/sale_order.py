"""Sale order form UI actions (Odoo 19)."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from cap_qa_platform.ui.data.so_cancel_data import SoCancelUiData
from cap_qa_platform.ui.pages.odoo_form import OdooFormHelper

if TYPE_CHECKING:
    from playwright.sync_api import Page


class SaleOrderPage:
    def __init__(self, page: Page):
        self.page = page
        self.form = OdooFormHelper(page)

    def open_sales_new_quotation(self) -> None:
        self.page.get_by_text("Sales", exact=True).first.click(timeout=30_000)
        self.page.wait_for_load_state("domcontentloaded")
        self.page.get_by_role("button", name="New").first.click(timeout=30_000)
        self.page.wait_for_load_state("domcontentloaded")
        self.page.locator(".o_field_widget[name='partner_id']").first.wait_for(
            state="visible", timeout=60_000
        )

    def fill_assistance_order(self, data: SoCancelUiData) -> None:
        self.form.dismiss_modals()
        self.form.select_many2one("partner_id", data.partner_name)
        self.form.select_many2one("business_unit_id", data.business_unit_name)
        self.form.select_many2one("business_localisation_id", data.business_localisation_name)
        self.form.select_many2one("offer_id", data.offer_name)
        self.form.dismiss_modals()
        for product_name in data.product_names:
            self._add_product_from_catalog(product_name)

    def _add_product_from_catalog(self, product_name: str) -> None:
        self.page.get_by_role("button", name="Catalog").click(timeout=30_000)
        self.page.wait_for_load_state("domcontentloaded")
        search = self.page.locator("input.o_searchview_input, .o_searchview input").first
        search.click()
        snippet = product_name if len(product_name) <= 30 else product_name[:30]
        search.fill(snippet)
        self.page.keyboard.press("Enter")
        self.page.wait_for_timeout(2000)
        card = self.page.locator(".o_kanban_record, article").filter(has_text=snippet[:20]).first
        card.get_by_role("button", name="Add").click(timeout=30_000)
        self.page.wait_for_timeout(1000)
        self.page.get_by_role("button", name="Back to Quotation").click(timeout=30_000)
        self.page.wait_for_load_state("domcontentloaded")
        self.page.locator(".o_field_widget[name='partner_id']").first.wait_for(
            state="visible", timeout=60_000
        )

    def confirm_order(self) -> None:
        self.form.dismiss_modals()
        self.form.click_button("Confirm")
        self.page.wait_for_load_state("domcontentloaded", timeout=120_000)
        self.page.locator(".o_statusbar_status").filter(has_text="Sales Order").first.wait_for(
            state="visible", timeout=120_000
        )

    def current_record_id(self) -> int:
        match = re.search(r"/odoo/sales/(\d+)", self.page.url)
        if not match:
            raise RuntimeError(f"Cannot parse sale order id from URL: {self.page.url}")
        return int(match.group(1))

    def link_project_create(self) -> None:
        btn = self.page.get_by_role("button", name="Create/Link Project")
        if btn.count():
            btn.click(timeout=30_000)
            self.form.confirm_modal("Submit")
            self.page.wait_for_load_state("domcontentloaded", timeout=120_000)
            return
        raise RuntimeError(
            "Create/Link Project button not visible in UI — use RPC fallback"
        )

    def cancel_order(self) -> None:
        self.form.dismiss_modals()
        self.page.locator(".o_statusbar_buttons button").filter(has_text="Cancel").first.click(
            timeout=30_000
        )
        dialog = self.page.locator(".modal-dialog:visible, .o_dialog:visible")
        dialog.wait_for(state="visible", timeout=15_000)
        for label in ("Ok", "OK", "Yes", "Submit", "Confirm"):
            btn = dialog.get_by_role("button", name=label)
            if btn.count():
                btn.first.click(timeout=10_000)
                break
        else:
            dialog.locator(".modal-footer button.btn-primary").first.click(timeout=10_000)
        self.page.wait_for_load_state("domcontentloaded", timeout=120_000)
