"""SO link project + invoice due 3 days ago → project color (ksc_project_extended)."""
from __future__ import annotations

from datetime import date, timedelta

from cap_qa_platform.rpc.client import OdooRPCClient, m2o_id
from cap_qa_platform.rpc.errors import RpcError
from cap_qa_platform.scenarios.base import ScenarioRunResult
from cap_qa_platform.scenarios.so_base import SoScenarioBase, _StepFailed

SCENARIO_NAME = "so_project_color_overdue_due_date"
REQUIRED_MODULES = (
    "ksc_project_extended",
    "ksc_sale_project_extended",
    "cap_offer",
    "sale",
)

# ksc_project_extended color indices
COLOR_ORANGE = 2
DAYS_AGO_DUE = 3


class SoProjectColorOverdueDueDateScenario(SoScenarioBase):
    def run(self, rpc: OdooRPCClient, role_name: str) -> ScenarioRunResult:
        result = ScenarioRunResult(scenario=SCENARIO_NAME, role_name=role_name, success=False)
        if not self.admin:
            result.failed_step = "setup"
            result.error = "Admin client required (bind_admin)."
            return result
        try:
            self._step(result, "assert_modules_installed", lambda: self._assert_modules(rpc))
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
                "assert_color_orange_due_three_days_ago",
                lambda: self._assert_project_color_overdue(
                    rpc, project_id, invoice_id, so_id
                ),
            )
            result.records = {
                "partner_id": partner_id,
                "sale_order_id": so_id,
                "project_id": project_id,
                "invoice_id": invoice_id,
                "invoice_due_date": (date.today() - timedelta(days=DAYS_AGO_DUE)).isoformat(),
                "expected_color": COLOR_ORANGE,
            }
            result.success = True
        except _StepFailed as exc:
            result.failed_step = exc.step
            result.error = exc.message
        return result

    def _assert_modules(self, rpc: OdooRPCClient) -> None:
        missing = []
        for module in REQUIRED_MODULES:
            if not rpc.search_count(
                "ir.module.module",
                [("name", "=", module), ("state", "=", "installed")],
            ):
                missing.append(module)
        if missing:
            raise AssertionError(f"Missing installed modules: {', '.join(missing)}")
        if "color" not in rpc.fields_get("project.project", attributes=["type"]):
            raise AssertionError("project.project.color field not found (ksc_project_extended).")

    def _ensure_posted_invoice(self, so_id: int, partner_id: int) -> int:
        assert self.admin is not None
        admin = self.admin
        inv_ids = list(admin.read("sale.order", [so_id], ["invoice_ids"])[0].get("invoice_ids") or [])
        if not inv_ids:
            created = admin.call("sale.order", "_create_invoices", [so_id])
            if isinstance(created, dict) and created.get("res_id"):
                inv_ids = [created["res_id"]]
            elif isinstance(created, int):
                inv_ids = [created]
            else:
                inv_ids = list(
                    admin.read("sale.order", [so_id], ["invoice_ids"])[0].get("invoice_ids") or []
                )
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
                "Check auto_invoice_confirm or invoicing rights."
            )
        invoice_id = inv_ids[0]
        if admin.read("account.move", [invoice_id], ["state"])[0].get("state") == "draft":
            admin.call("account.move", "action_post", [invoice_id])
        return invoice_id

    def _find_products_for_color_test(self, rpc: OdooRPCClient, offer_id: int) -> list[dict]:
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
            p for p in products if uom_name(p) in ("Hours", "Working Time", "Temps de travail")
        ]
        non_prepaid = [
            p for p in products if p.get("service_policy") and p.get("service_policy") != "ordered_prepaid"
        ]
        if len(hour_products) >= 2:
            return hour_products[:2]
        if non_prepaid:
            other = next((p for p in products if p["id"] != non_prepaid[0]["id"]), products[0])
            return [non_prepaid[0], other]
        return products[:2]

    def _prepare_project_for_invoice_color(self, project_id: int, so_id: int) -> None:
        assert self.admin is not None
        self.admin.write("project.project", [project_id], {"on_hold_reason": False})
        line_ids = self.admin.search("sale.order.line", [("order_id", "=", so_id)])
        if not line_ids:
            return
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

    def _assert_project_color_overdue(
        self,
        rpc: OdooRPCClient,
        project_id: int,
        invoice_id: int,
        so_id: int,
    ) -> None:
        assert self.admin is not None
        self._prepare_project_for_invoice_color(project_id, so_id)
        due = date.today() - timedelta(days=DAYS_AGO_DUE)
        self.admin.write(
            "account.move",
            [invoice_id],
            {"invoice_date_due": due.isoformat()},
        )
        self.admin.call(
            "project.project",
            "compute_project_color_remaining_hours",
            [project_id],
        )
        project = rpc.read(
            "project.project",
            [project_id],
            ["color", "on_hold_reason", "name"],
        )[0]
        actual = project.get("color")
        if actual != COLOR_ORANGE:
            raise AssertionError(
                f"Project {project_id} color={actual}, expected {COLOR_ORANGE} "
                f"(invoice due {DAYS_AGO_DUE} days ago on {due.isoformat()}, "
                f"on_hold={project.get('on_hold_reason')!r})."
            )
