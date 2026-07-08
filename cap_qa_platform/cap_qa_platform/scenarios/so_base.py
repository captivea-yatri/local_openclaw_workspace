"""Shared sale-order scenario helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from cap_qa_platform.rpc.client import OdooRPCClient, m2o_id
from cap_qa_platform.rpc.errors import RpcError, is_access_error
from cap_qa_platform.scenarios.base import ScenarioRunResult, StepOutcome


def unique_suffix() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")[:15]


class SoScenarioBase:
    def __init__(self, no_cleanup: bool = False, fallback_partner_id: int | None = None):
        self.no_cleanup = no_cleanup
        self.fallback_partner_id = fallback_partner_id
        self.admin: OdooRPCClient | None = None
        self.suffix = unique_suffix()
        self.company_id: int | None = None
        self.team_id: int | False = False
        self.cleanup_tracker: list[tuple[str, int]] = []
        self.used_existing_partner = False

    def bind_admin(self, admin: OdooRPCClient) -> None:
        self.admin = admin

    def _track(self, model: str, record_id: int) -> None:
        if not self.no_cleanup:
            self.cleanup_tracker.append((model, record_id))

    def _step(self, result: ScenarioRunResult, step: str, fn):
        try:
            value = fn()
            result.steps.append(StepOutcome(step=step, ok=True))
            return value
        except Exception as exc:
            result.steps.append(StepOutcome(step=step, ok=False, error=str(exc)))
            raise _StepFailed(step, str(exc)) from exc

    def _authenticate(self, rpc: OdooRPCClient) -> None:
        user = rpc.read("res.users", [rpc.uid], ["company_id"])[0]
        self.company_id = m2o_id(user.get("company_id"))
        if not self.company_id:
            raise RpcError("RPC user has no default company_id.")
        self.team_id = False
        for domain in (
            [("company_id", "=", self.company_id)],
            [("company_id", "=", False)],
        ):
            try:
                teams = rpc.search_read("crm.team", domain, ["id"], limit=1)
                if teams:
                    self.team_id = teams[0]["id"]
                    break
            except RpcError as exc:
                if not is_access_error(exc):
                    raise

    def _resolve_partner(self, rpc: OdooRPCClient, result: ScenarioRunResult) -> int:
        try:
            partner_id = self._create_partner(rpc)
            result.steps.append(StepOutcome(step="create_partner", ok=True))
            return partner_id
        except Exception as exc:
            if not is_access_error(exc):
                result.steps.append(
                    StepOutcome(step="create_partner", ok=False, error=str(exc))
                )
                raise _StepFailed("create_partner", str(exc)) from exc
            result.steps.append(
                StepOutcome(step="create_partner", ok=False, error=f"no create access: {exc}")
            )
        partner_id = self._find_usable_partner(rpc)
        if not partner_id and self.fallback_partner_id:
            partner_id = self._verify_partner_readable(rpc, self.fallback_partner_id)
        if not partner_id:
            raise _StepFailed(
                "use_existing_partner",
                "Cannot create partner and no readable existing partner found.",
            )
        self.used_existing_partner = True
        result.steps.append(StepOutcome(step="use_existing_partner", ok=True))
        return partner_id

    def _verify_partner_readable(self, rpc: OdooRPCClient, partner_id: int) -> int | None:
        try:
            rows = rpc.read("res.partner", [partner_id], ["id"])
            return rows[0]["id"] if rows else None
        except RpcError:
            return None

    def _find_usable_partner(self, rpc: OdooRPCClient) -> int | None:
        for domain in (
            [("is_company", "=", True), ("company_id", "in", [self.company_id, False])],
            [("is_company", "=", True)],
            [("customer_rank", ">", 0)],
            [],
        ):
            try:
                partners = rpc.search_read(
                    "res.partner", domain, ["id", "is_company"], limit=10, order="id desc"
                )
            except RpcError:
                continue
            for partner in partners:
                if partner.get("is_company"):
                    return partner["id"]
            if partners:
                return partners[0]["id"]
        return None

    def _create_partner(self, rpc: OdooRPCClient) -> int:
        partner_id = rpc.create(
            "res.partner",
            {
                "name": f"CAPQA_Partner_{self.suffix}",
                "company_type": "company",
                "is_company": True,
                "company_id": self.company_id,
            },
        )
        self._track("res.partner", partner_id)
        return partner_id

    def _find_assistance_offer(self, rpc: OdooRPCClient) -> dict[str, Any]:
        offer_fields = rpc.fields_get("offer.offer", attributes=["type"])
        type_field = next(
            (c for c in ("type", "x_studio_type") if c in offer_fields),
            None,
        )
        domain_list = []
        if type_field:
            domain_list.append([(type_field, "=", "assistance")])
        domain_list.append([("name", "ilike", "assistance")])
        for domain in domain_list:
            offers = rpc.search_read(
                "offer.offer",
                domain,
                ["id", "name", "business_unit_ids", "business_localisation_ids"],
                limit=1,
            )
            if offers:
                return offers[0]
        raise RpcError("Assistance offer not found (cap_offer).")

    def _find_two_service_products(self, rpc: OdooRPCClient, offer_id: int) -> list[dict]:
        fields = ["id", "name", "uom_id", "lst_price", "minimumSalePrice"]
        fg = rpc.fields_get("product.product", attributes=["type"])
        if "minimumSalePrice" not in fg:
            fields = [f for f in fields if f != "minimumSalePrice"]
        products = rpc.search_read(
            "product.product",
            [("offer_ids", "in", [offer_id]), ("type", "=", "service"), ("sale_ok", "=", True)],
            fields,
            limit=2,
        )
        if len(products) < 2:
            raise RpcError("Need two service products linked to the offer.")
        return products

    def _order_line_vals(self, product: dict) -> dict:
        uom_id = m2o_id(product.get("uom_id"))
        if not uom_id:
            raise RpcError(f"Product {product['id']} has no UoM.")
        price = product.get("lst_price") or 1.0
        minimum = product.get("minimumSalePrice")
        if minimum and price < minimum:
            price = minimum
        return {
            "product_id": product["id"],
            "product_uom_qty": 1.0,
            "product_uom_id": uom_id,
            "price_unit": price,
        }

    def _create_sale_order(
        self, rpc: OdooRPCClient, partner_id: int, offer: dict, products: list[dict]
    ) -> int:
        bu_id = m2o_id(offer.get("business_unit_ids"))
        loc_id = m2o_id(offer.get("business_localisation_ids"))
        if not bu_id:
            bu_ids = offer.get("business_unit_ids") or []
            bu_id = bu_ids[0] if bu_ids else None
        if not loc_id:
            loc_ids = offer.get("business_localisation_ids") or []
            loc_id = loc_ids[0] if loc_ids else None
        if not bu_id or not loc_id:
            raise RpcError("Offer missing business unit or localisation.")
        order_vals = {
            "partner_id": partner_id,
            "company_id": self.company_id,
            "business_unit_id": bu_id,
            "business_localisation_id": loc_id,
            "offer_id": offer["id"],
            "order_line": [
                (0, 0, self._order_line_vals(products[0])),
                (0, 0, self._order_line_vals(products[1])),
            ],
        }
        if self.team_id:
            order_vals["team_id"] = self.team_id
        so_id = rpc.create("sale.order", order_vals)
        self._track("sale.order", so_id)
        return so_id

    def _confirm_sale_order(self, rpc: OdooRPCClient, so_id: int) -> None:
        rpc.call("sale.order", "action_confirm", [so_id])

    def _create_link_project(self, rpc: OdooRPCClient, so_id: int) -> int:
        wiz_id = rpc.create("link.so.project.wizard", {"operation": "create"})
        rpc.call(
            "link.so.project.wizard",
            "link_so_project",
            [wiz_id],
            context={
                "active_model": "sale.order",
                "active_id": so_id,
                "active_ids": [so_id],
            },
        )
        project_id = self._resolve_project_id(rpc, so_id)
        if not project_id:
            raise AssertionError("Project not linked after wizard.")
        self._track("project.project", project_id)
        return project_id

    def _resolve_project_id(self, rpc: OdooRPCClient, so_id: int) -> int | None:
        lines = rpc.search_read("sale.order.line", [("order_id", "=", so_id)], ["project_id"])
        for line in lines:
            project_id = m2o_id(line.get("project_id"))
            if project_id:
                return project_id
        so = rpc.read("sale.order", [so_id], ["partner_id"])[0]
        partner_id = m2o_id(so.get("partner_id"))
        projects = rpc.search(
            "project.project",
            [("partner_id", "=", partner_id)],
            limit=1,
            order="id desc",
        )
        return projects[0] if projects else None

    def cleanup_as_admin(self, admin: OdooRPCClient) -> None:
        from cap_qa_platform.rpc.errors import RpcError

        for model, record_id in reversed(self.cleanup_tracker):
            if model == "sale.order":
                try:
                    rows = admin.read("sale.order", [record_id], ["state"])
                    if rows and rows[0].get("state") in ("sale", "done"):
                        admin.call("sale.order", "action_cancel", [record_id])
                except RpcError:
                    pass
        for model, record_id in reversed(self.cleanup_tracker):
            try:
                admin.unlink(model, [record_id])
            except RpcError:
                pass
        self.cleanup_tracker.clear()


class _StepFailed(Exception):
    def __init__(self, step: str, message: str):
        self.step = step
        self.message = message
        super().__init__(message)
