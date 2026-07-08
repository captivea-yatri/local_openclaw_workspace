"""
SO cancel → old_customer scenario.

Modules involved:
  - cap_partner          : res.partner.status, customer lifecycle
  - cap_offer            : offer_id, business_unit_id, business_localisation_id on sale.order
  - ksc_sale_project_extended : link.so.project.wizard, project linking
  - cap_quality_issue_log: quality.issue.log on Customer Lost automation
  - base_user_role       : role → group sync for test user
  - access_rights_management : role definitions (roles_data.xml)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from test_automation.rpc.client import OdooRPCClient, m2o_id
from test_automation.rpc.errors import RpcError, is_access_error
from test_automation.scenarios.base import ScenarioRunResult, StepOutcome

SCENARIO_NAME = "so_cancel_old_customer"

STEPS = (
    "create_partner",
    "use_existing_partner",
    "create_sale_order",
    "action_confirm",
    "assert_customer_status",
    "link_so_project",
    "assign_project_user",
    "action_cancel",
    "assert_old_customer_status",
    "assert_quality_logs",
)


def _unique_suffix() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")[:15]


class SoCancelOldCustomerScenario:
    def __init__(
        self,
        no_cleanup: bool = False,
        assign_project_pm: bool = True,
        fallback_partner_id: int | None = None,
    ):
        self.no_cleanup = no_cleanup
        self.assign_project_pm = assign_project_pm
        self.fallback_partner_id = fallback_partner_id
        self.suffix = _unique_suffix()
        self.company_id: int | None = None
        self.team_id: int | False = False
        self.cleanup_tracker: list[tuple[str, int]] = []
        self.used_existing_partner = False

    def _track(self, model: str, record_id: int) -> None:
        if not self.no_cleanup:
            self.cleanup_tracker.append((model, record_id))

    def run(self, rpc: OdooRPCClient, role_name: str) -> ScenarioRunResult:
        result = ScenarioRunResult(
            scenario=SCENARIO_NAME,
            role_name=role_name,
            success=False,
        )
        try:
            self._authenticate(rpc)
            partner_id = self._resolve_partner(rpc, result)
            offer = self._find_assistance_offer(rpc)
            products = self._find_two_service_products(rpc, offer["id"])
            so_id = self._step(
                result,
                "create_sale_order",
                lambda: self._create_sale_order(rpc, partner_id, offer, products),
            )
            self._step(result, "action_confirm", lambda: self._confirm_sale_order(rpc, so_id))
            self._step(
                result,
                "assert_customer_status",
                lambda: self._assert_partner_status(rpc, partner_id, "customer"),
            )
            project_id = self._step(
                result, "link_so_project", lambda: self._create_link_project(rpc, so_id)
            )
            if self.assign_project_pm:
                self._step(
                    result,
                    "assign_project_user",
                    lambda: self._assign_project_user(rpc, project_id),
                )
            self._step(result, "action_cancel", lambda: self._cancel_sale_order(rpc, so_id))
            self._step(
                result,
                "assert_old_customer_status",
                lambda: self._assert_partner_status(rpc, partner_id, "old_customer"),
            )
            count = self._step(
                result,
                "assert_quality_logs",
                lambda: self._count_quality_logs(rpc, project_id),
            )
            result.quality_log_count = count
            result.records = {
                "partner_id": partner_id,
                "sale_order_id": so_id,
                "project_id": project_id,
                "used_existing_partner": self.used_existing_partner,
            }
            result.success = True
        except _StepFailed as exc:
            result.failed_step = exc.step
            result.error = exc.message
        return result

    def cleanup_as_admin(self, admin: OdooRPCClient) -> None:
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
                StepOutcome(
                    step="create_partner",
                    ok=False,
                    error=f"no create access: {exc}",
                )
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
            rows = rpc.read("res.partner", [partner_id], ["id", "name", "is_company"])
            if rows:
                return rows[0]["id"]
        except RpcError:
            pass
        return None

    def _find_usable_partner(self, rpc: OdooRPCClient) -> int | None:
        """Pick a company partner the current user can read (for SO creation)."""
        domains = [
            [("is_company", "=", True), ("company_id", "in", [self.company_id, False])],
            [("is_company", "=", True)],
            [("customer_rank", ">", 0)],
            [],
        ]
        for domain in domains:
            try:
                partners = rpc.search_read(
                    "res.partner",
                    domain,
                    ["id", "name", "is_company"],
                    limit=10,
                    order="id desc",
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
        name = f"TestPartner_{self.suffix}"
        partner_id = rpc.create(
            "res.partner",
            {
                "name": name,
                "company_type": "company",
                "is_company": True,
                "company_id": self.company_id,
            },
        )
        self._track("res.partner", partner_id)
        return partner_id

    def _find_assistance_offer(self, rpc: OdooRPCClient) -> dict[str, Any]:
        offer_fields = rpc.fields_get("offer.offer", attributes=["type"])
        type_field = None
        for candidate in ("type", "x_studio_type"):
            if candidate in offer_fields:
                type_field = candidate
                break
        offers = []
        if type_field:
            offers = rpc.search_read(
                "offer.offer",
                [(type_field, "=", "assistance")],
                ["id", "name", "business_unit_ids", "business_localisation_ids"],
                limit=1,
            )
        if not offers:
            offers = rpc.search_read(
                "offer.offer",
                [("name", "ilike", "assistance")],
                ["id", "name", "business_unit_ids", "business_localisation_ids"],
                limit=1,
            )
        if not offers:
            raise RpcError("Assistance offer not found (cap_offer).")
        return offers[0]

    def _find_two_service_products(self, rpc: OdooRPCClient, offer_id: int) -> list[dict]:
        fields = ["id", "name", "uom_id", "lst_price", "minimumSalePrice"]
        if "minimumSalePrice" not in rpc.fields_get("product.product", attributes=["type"]):
            fields = [f for f in fields if f != "minimumSalePrice"]
        products = rpc.search_read(
            "product.product",
            [
                ("offer_ids", "in", [offer_id]),
                ("type", "=", "service"),
                ("sale_ok", "=", True),
            ],
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
        self,
        rpc: OdooRPCClient,
        partner_id: int,
        offer: dict,
        products: list[dict],
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
            raise RpcError("Offer missing business unit or localisation (cap_offer).")
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

    def _cancel_sale_order(self, rpc: OdooRPCClient, so_id: int) -> None:
        rpc.call("sale.order", "action_cancel", [so_id])

    def _assert_partner_status(
        self, rpc: OdooRPCClient, partner_id: int, expected: str
    ) -> None:
        partner = rpc.read("res.partner", [partner_id], ["status"])[0]
        actual = partner.get("status")
        if actual != expected:
            raise AssertionError(f"Partner status '{actual}', expected '{expected}'.")

    def _resolve_project_id(self, rpc: OdooRPCClient, so_id: int) -> int | None:
        lines = rpc.search_read(
            "sale.order.line", [("order_id", "=", so_id)], ["project_id"]
        )
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
            raise AssertionError("Project not linked after wizard (ksc_sale_project_extended).")
        self._track("project.project", project_id)
        return project_id

    def _assign_project_user(self, rpc: OdooRPCClient, project_id: int) -> None:
        rpc.write("project.project", [project_id], {"user_id": rpc.uid})
        project = rpc.read("project.project", [project_id], ["user_id"])[0]
        if m2o_id(project.get("user_id")) != rpc.uid:
            raise AssertionError(f"Project {project_id} user_id not set.")

    def _count_quality_logs(self, rpc: OdooRPCClient, project_id: int) -> int:
        return rpc.search_count(
            "quality.issue.log",
            [("project_id", "=", project_id)],
        )


class _StepFailed(Exception):
    def __init__(self, step: str, message: str):
        self.step = step
        self.message = message
        super().__init__(message)
