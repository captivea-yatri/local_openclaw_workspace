"""SO link project + invoice color scenario."""
from __future__ import annotations

from datetime import date, timedelta

from cap_qa_platform.rpc.client import OdooRPCClient, m2o_id
from cap_qa_platform.rpc.errors import RpcError
from cap_qa_platform.scenarios.base import ScenarioRunResult
from cap_qa_platform.scenarios.so_base import SoScenarioBase, _StepFailed

SCENARIO_NAME = "so_link_project_invoice_color"
COLOR_GREEN = 10
COLOR_ORANGE = 2


class SoLinkProjectInvoiceColorScenario(SoScenarioBase):
    def run(self, rpc: OdooRPCClient, role_name: str) -> ScenarioRunResult:
        result = ScenarioRunResult(scenario=SCENARIO_NAME, role_name=role_name, success=False)
        if not self.admin:
            result.failed_step = "setup"
            result.error = "Admin client required (bind_admin)."
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
            }
            result.success = True
        except _StepFailed as exc:
            result.failed_step = exc.step
            result.error = exc.message
        return result

    def _ensure_posted_invoice(self, so_id: int, partner_id: int) -> int:
        assert self.admin is not None
        admin = self.admin
        so = admin.read("sale.order", [so_id], ["invoice_ids"])[0]
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
            raise RpcError("No invoice after link project.")
        invoice_id = inv_ids[0]
        inv = admin.read("account.move", [invoice_id], ["state"])[0]
        if inv.get("state") == "draft":
            admin.call("account.move", "action_post", [invoice_id])
        return invoice_id

    def _find_products_for_color_test(self, rpc: OdooRPCClient, offer_id: int) -> list[dict]:
        fields = ["id", "name", "uom_id", "lst_price", "service_policy"]
        fg = rpc.fields_get("product.product", attributes=["type"])
        if "service_policy" not in fg:
            fields = [f for f in fields if f != "service_policy"]
        products = rpc.search_read(
            "product.product",
            [("offer_ids", "in", [offer_id]), ("type", "=", "service"), ("sale_ok", "=", True)],
            fields,
            limit=30,
        )
        if len(products) < 2:
            raise RpcError("Need two service products on the offer.")
        return products[:2]

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
        due = date.today() + timedelta(days=days_until_due)
        self.admin.write("account.move", [invoice_id], {"invoice_date_due": due.isoformat()})
        self.admin.call(
            "project.project",
            "compute_project_color_remaining_hours",
            [project_id],
        )
        project = rpc.read("project.project", [project_id], ["color"])[0]
        if project.get("color") != expected_color:
            raise AssertionError(
                f"Project color={project.get('color')}, expected {expected_color}."
            )
