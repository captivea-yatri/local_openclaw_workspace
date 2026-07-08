"""SO cancel → old_customer scenario."""
from __future__ import annotations

from cap_qa_platform.rpc.client import OdooRPCClient, m2o_id
from cap_qa_platform.rpc.errors import RpcError
from cap_qa_platform.rpc.tester_employee import ensure_tester_employee
from cap_qa_platform.scenarios.base import ScenarioRunResult
from cap_qa_platform.scenarios.so_base import SoScenarioBase, _StepFailed, unique_suffix

SCENARIO_NAME = "so_cancel_old_customer"


class SoCancelOldCustomerScenario(SoScenarioBase):
    def __init__(
        self,
        no_cleanup: bool = False,
        assign_project_pm: bool = True,
        fallback_partner_id: int | None = None,
    ):
        super().__init__(no_cleanup=no_cleanup, fallback_partner_id=fallback_partner_id)
        self.assign_project_pm = assign_project_pm
        self.suffix = unique_suffix()

    def run(self, rpc: OdooRPCClient, role_name: str) -> ScenarioRunResult:
        result = ScenarioRunResult(scenario=SCENARIO_NAME, role_name=role_name, success=False)
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
            }
            result.success = True
        except _StepFailed as exc:
            result.failed_step = exc.step
            result.error = exc.message
        return result

    def _cancel_sale_order(self, rpc: OdooRPCClient, so_id: int) -> None:
        rpc.call("sale.order", "action_cancel", [so_id])

    def _assert_partner_status(self, rpc: OdooRPCClient, partner_id: int, expected: str) -> None:
        partner = rpc.read("res.partner", [partner_id], ["status"])[0]
        if partner.get("status") != expected:
            raise AssertionError(
                f"Partner status '{partner.get('status')}', expected '{expected}'."
            )

    def _assign_project_user(self, rpc: OdooRPCClient, project_id: int) -> None:
        if not self.admin:
            raise RpcError("Admin client required to ensure hr.employee for test user.")
        ensure_tester_employee(
            self.admin,
            rpc.uid,
            self.company_id,
            track=self._track if not self.no_cleanup else None,
        )
        rpc.write("project.project", [project_id], {"user_id": rpc.uid})
        project = rpc.read("project.project", [project_id], ["user_id"])[0]
        if m2o_id(project.get("user_id")) != rpc.uid:
            raise AssertionError(f"Project {project_id} user_id not set.")

    def _count_quality_logs(self, rpc: OdooRPCClient, project_id: int) -> int:
        count = rpc.search_count(
            "quality.issue.log", [("project_id", "=", project_id)]
        )
        if count < 1:
            raise AssertionError(
                f"Expected at least 1 quality.issue.log for project {project_id}, found {count}."
            )
        return count
