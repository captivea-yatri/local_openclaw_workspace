"""
SO confirm → link project → invoice → project color by due date.

Modules:
  - ksc_sale_project_extended : link_so_project wizard, auto_invoice_confirm
  - ksc_project_extended      : compute_project_color_remaining_hours
  - cap_offer                 : offer / BU / localisation on SO

Color index (ksc_project_extended):
  10 = green (normal)
   2 = orange (invoice due within 5 days, grace period, etc.)
   1 = red (blocked / late payment)
"""
from __future__ import annotations

from datetime import date, timedelta

from test_automation.rpc.client import OdooRPCClient, m2o_id
from test_automation.rpc.errors import RpcError
from test_automation.scenarios.base import ScenarioRunResult
from test_automation.scenarios.so_base import SoScenarioBase, _StepFailed

SCENARIO_NAME = "so_link_project_invoice_color"

COLOR_GREEN = 10
COLOR_ORANGE = 2
COLOR_RED = 1


class SoLinkProjectInvoiceColorScenario(SoScenarioBase):
    def __init__(
        self,
        no_cleanup: bool = False,
        fallback_partner_id: int | None = None,
        **kwargs,
    ):
        super().__init__(no_cleanup=no_cleanup, fallback_partner_id=fallback_partner_id)

    def run(self, rpc: OdooRPCClient, role_name: str) -> ScenarioRunResult:
        result = ScenarioRunResult(scenario=SCENARIO_NAME, role_name=role_name, success=False)
        if not self.admin:
            result.failed_step = "setup"
            result.error = "Admin client required for invoice/color setup (bind_admin)."
            return result
        try:
            self._authenticate(rpc)
            partner_id = self._resolve_partner(rpc, result)
            offer = self._find_assistance_offer(rpc)
            products = self._find_products_for_color_test(rpc, offer["id"])
            so_id = self._step(
                result,
                "create_sale_order",
                lambda: self._create_sale_order(rpc, partner_id, offer, products),
            )
            self._step(result, "action_confirm", lambda: self._confirm_sale_order(rpc, so_id))
            project_id = self._step(
                result,
                "link_so_project",
                lambda: self._create_link_project(rpc, so_id),
            )
            invoice_id = self._step(
                result,
                "ensure_posted_invoice",
                lambda: self._ensure_posted_invoice(so_id, partner_id),
            )
            self._step(
                result,
                "assert_color_orange_due_soon",
                lambda: self._assert_project_color(
                    rpc, project_id, invoice_id, so_id, 3, COLOR_ORANGE
                ),
            )
            self._step(
                result,
                "assert_color_green_far_due",
                lambda: self._assert_project_color(
                    rpc, project_id, invoice_id, so_id, 30, COLOR_GREEN
                ),
            )
            result.records = {
                "partner_id": partner_id,
                "sale_order_id": so_id,
                "project_id": project_id,
                "invoice_id": invoice_id,
                "used_existing_partner": self.used_existing_partner,
            }
            result.success = True
        except _StepFailed as exc:
            result.failed_step = exc.step
            result.error = exc.message
        return result

    def _ensure_posted_invoice(self, so_id: int, partner_id: int) -> int:
        assert self.admin is not None
        admin = self.admin
        so = admin.read("sale.order", [so_id], ["name", "invoice_ids"])[0]
        inv_ids = list(so.get("invoice_ids") or [])
        if not inv_ids:
            created = admin.call("sale.order", "_create_invoices", [so_id])
            if isinstance(created, dict) and created.get("res_id"):
                inv_ids = [created["res_id"]]
            elif isinstance(created, int):
                inv_ids = [created]
            else:
                so = admin.read("sale.order", [so_id], ["invoice_ids"])[0]
                inv_ids = list(so.get("invoice_ids") or [])
        if not inv_ids:
            inv_ids = admin.search(
                "account.move",
                [
                    ("partner_id", "child_of", partner_id),
                    ("move_type", "=", "out_invoice"),
                    ("state", "!=", "cancel"),
                ],
                limit=1,
                order="id desc",
            )
        if not inv_ids:
            raise RpcError(
                "No invoice after link project. "
                "Check auto_invoice_confirm (ordered_prepaid lines) or invoicing rights."
            )
        invoice_id = inv_ids[0]
        inv = admin.read("account.move", [invoice_id], ["state"])[0]
        if inv.get("state") == "draft":
            admin.call("account.move", "action_post", [invoice_id])
        return invoice_id

    def _find_products_for_color_test(self, rpc: OdooRPCClient, offer_id: int) -> list[dict]:
        """Pick lines so project hours logic does not force red (no_hours) before invoice color."""
        fields = ["id", "name", "uom_id", "lst_price", "service_policy"]
        fg = rpc.fields_get("product.product", attributes=["type"])
        if "service_policy" not in fg:
            fields = [f for f in fields if f != "service_policy"]
        products = rpc.search_read(
            "product.product",
            [
                ("offer_ids", "in", [offer_id]),
                ("type", "=", "service"),
                ("sale_ok", "=", True),
            ],
            fields,
            limit=30,
        )
        if len(products) < 2:
            raise RpcError("Need two service products on the assistance offer.")

        def uom_name(product: dict) -> str:
            uom_id = m2o_id(product.get("uom_id"))
            if not uom_id:
                return ""
            return rpc.read("uom.uom", [uom_id], ["name"])[0].get("name") or ""

        hour_products = [
            p for p in products
            if uom_name(p) in ("Hours", "Working Time", "Temps de travail")
        ]
        non_prepaid = [
            p for p in products
            if p.get("service_policy") and p.get("service_policy") != "ordered_prepaid"
        ]
        if len(hour_products) >= 2:
            return hour_products[:2]
        if non_prepaid:
            other = next((p for p in products if p["id"] != non_prepaid[0]["id"]), products[0])
            return [non_prepaid[0], other]
        return products[:2]

    def _prepare_project_for_invoice_color(self, project_id: int, so_id: int) -> None:
        """Clear hour-hold side effects so invoice due date drives orange/green."""
        assert self.admin is not None
        self.admin.write("project.project", [project_id], {"on_hold_reason": False})
        line_ids = self.admin.search(
            "sale.order.line",
            [("order_id", "=", so_id)],
        )
        if line_ids:
            updates = {"x_studio_consumed_qty": 0}
            lines = self.admin.read(
                "sale.order.line", line_ids, ["product_uom_id", "product_uom_qty"]
            )
            for line in lines:
                uom_id = m2o_id(line.get("product_uom_id"))
                if uom_id:
                    uom = self.admin.read("uom.uom", [uom_id], ["name"])[0]
                    if uom.get("name") in ("Hours", "Working Time", "Temps de travail"):
                        updates["product_uom_qty"] = max(line.get("product_uom_qty") or 1, 10)
            self.admin.write("sale.order.line", line_ids, updates)

    def _assert_project_color(
        self,
        rpc: OdooRPCClient,
        project_id: int,
        invoice_id: int,
        so_id: int,
        days_until_due: int,
        expected_color: int,
    ) -> None:
        assert self.admin is not None
        self._prepare_project_for_invoice_color(project_id, so_id)
        due = date.today() + timedelta(days=days_until_due)
        self.admin.write(
            "account.move",
            [invoice_id],
            {"invoice_date_due": due.isoformat()},
        )
        self._recompute_project_color(project_id)
        project = rpc.read(
            "project.project",
            [project_id],
            ["color", "on_hold_reason", "name"],
        )[0]
        actual = project.get("color")
        if actual != expected_color:
            raise AssertionError(
                f"Project {project_id} color={actual}, expected {expected_color} "
                f"(due in {days_until_due} days, on_hold={project.get('on_hold_reason')!r})."
            )

    def _recompute_project_color(self, project_id: int) -> None:
        assert self.admin is not None
        self.admin.call(
            "project.project",
            "compute_project_color_remaining_hours",
            [project_id],
        )
