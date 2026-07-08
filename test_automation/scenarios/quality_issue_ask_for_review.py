"""
Quality issue log — Ask For Review (current module behavior).

Modules:
  - cap_quality_issue_log : quality.issue.log.ask_for_review

Current production code creates a legacy To-Do mail.activity on quality.issue.log
for the employee's manager and sets state=reviewing. It does NOT create
approval.request (that workflow is tested separately in
cap_quality_issue_log/scripts/test_quality_issue_approval_rpc.py).
"""
from __future__ import annotations

from datetime import date

from test_automation.rpc.client import OdooRPCClient, m2o_id
from test_automation.rpc.errors import RpcError
from test_automation.scenarios.base import ScenarioRunResult, StepOutcome
from test_automation.scenarios.so_base import _StepFailed, unique_suffix

SCENARIO_NAME = "quality_issue_ask_for_review"

ACTIVITY_SUMMARY = "Review Quality Issue"


class QualityIssueAskForReviewScenario:
    def __init__(
        self,
        no_cleanup: bool = False,
        fallback_partner_id: int | None = None,
        **kwargs,
    ):
        self.no_cleanup = no_cleanup
        self.admin: OdooRPCClient | None = None
        self.suffix = unique_suffix()
        self.cleanup_tracker: list[tuple[str, int]] = []
        self._manager_user_id: int | None = None

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

    def run(self, rpc: OdooRPCClient, role_name: str) -> ScenarioRunResult:
        result = ScenarioRunResult(scenario=SCENARIO_NAME, role_name=role_name, success=False)
        if not self.admin:
            result.failed_step = "setup"
            result.error = "Admin client required (bind_admin)."
            return result
        try:
            ctx = self._step(result, "setup_quality_log", lambda: self._setup(rpc))
            self._step(
                result,
                "ask_for_review",
                lambda: self._ask_for_review(rpc, ctx["quality_log_id"]),
            )
            self._step(
                result,
                "assert_state_reviewing",
                lambda: self._assert_state(rpc, ctx["quality_log_id"], "reviewing"),
            )
            activity_ids = self._step(
                result,
                "assert_manager_todo_on_qil",
                lambda: self._assert_manager_todo_on_qil(ctx),
            )
            self._step(
                result,
                "assert_no_approval_request",
                lambda: self._assert_no_approval_request(ctx["quality_log_id"]),
            )
            result.records = {
                **ctx,
                "activity_ids": activity_ids,
                "manager_user_id": ctx["manager_user_id"],
                "approval_request_ids": [],
            }
            result.success = True
        except _StepFailed as exc:
            result.failed_step = exc.step
            result.error = exc.message
        return result

    def cleanup_as_admin(self, admin: OdooRPCClient) -> None:
        for model, record_id in reversed(self.cleanup_tracker):
            try:
                admin.unlink(model, [record_id])
            except RpcError:
                pass
        self.cleanup_tracker.clear()

    def _company_id(self) -> int:
        assert self.admin is not None
        user = self.admin.read("res.users", [self.admin.uid], ["company_id"])[0]
        company_id = m2o_id(user.get("company_id"))
        if not company_id:
            raise RpcError("Admin has no company_id.")
        return company_id

    def _setup(self, rpc: OdooRPCClient) -> dict:
        assert self.admin is not None
        admin = self.admin
        company_id = self._company_id()

        manager_login = f"qil_mgr_{self.suffix}@matrix.test"
        manager_ids = admin.search("res.users", [("login", "=", manager_login)], limit=1)
        if manager_ids:
            manager_user_id = manager_ids[0]
        else:
            manager_user_id = admin.create(
                "res.users",
                {
                    "name": f"QIL Manager {self.suffix}",
                    "login": manager_login,
                    "password": "feature_matrix_test",
                    "company_id": company_id,
                    "company_ids": [(6, 0, [company_id])],
                },
            )
            self._track("res.users", manager_user_id)
        self._manager_user_id = manager_user_id

        manager_emp_ids = admin.search(
            "hr.employee", [("user_id", "=", manager_user_id)], limit=1
        )
        if manager_emp_ids:
            manager_employee_id = manager_emp_ids[0]
        else:
            manager_employee_id = admin.create(
                "hr.employee",
                {
                    "name": f"QIL Manager {self.suffix}",
                    "user_id": manager_user_id,
                    "company_id": company_id,
                },
            )
            self._track("hr.employee", manager_employee_id)

        emp_ids = admin.search("hr.employee", [("user_id", "=", rpc.uid)], limit=1)
        if emp_ids:
            employee_id = emp_ids[0]
            admin.write(
                "hr.employee",
                [employee_id],
                {"parent_id": manager_employee_id, "company_id": company_id},
            )
        else:
            employee_id = admin.create(
                "hr.employee",
                {
                    "name": f"Matrix Employee {self.suffix}",
                    "user_id": rpc.uid,
                    "company_id": company_id,
                    "parent_id": manager_employee_id,
                },
            )
            self._track("hr.employee", employee_id)

        issue_types = admin.search_read(
            "quality.issue.type", [], ["id", "score_impact"], limit=1
        )
        if issue_types:
            issue_type_id = issue_types[0]["id"]
            score = issue_types[0].get("score_impact") or 5.0
        else:
            issue_type_id = admin.create(
                "quality.issue.type",
                {
                    "name": f"Matrix QIL Type {self.suffix}",
                    "score_impact": 5.0,
                    "state": "in_progress",
                },
            )
            self._track("quality.issue.type", issue_type_id)
            score = 5.0

        quality_log_id = admin.create(
            "quality.issue.log",
            {
                "logged_date": date.today().isoformat(),
                "employee_id": employee_id,
                "description": f"Matrix test QIL {self.suffix}",
                "score_impact": score,
                "quality_issue_type": issue_type_id,
                "log_type": "penalty",
                "state": "enabled",
            },
        )
        self._track("quality.issue.log", quality_log_id)

        return {
            "quality_log_id": quality_log_id,
            "employee_id": employee_id,
            "manager_user_id": manager_user_id,
            "manager_employee_id": manager_employee_id,
        }

    def _ask_for_review(self, rpc: OdooRPCClient, quality_log_id: int) -> None:
        rpc.call("quality.issue.log", "ask_for_review", [quality_log_id])

    def _assert_state(self, rpc: OdooRPCClient, quality_log_id: int, expected: str) -> None:
        row = rpc.read("quality.issue.log", [quality_log_id], ["state"])[0]
        if row.get("state") != expected:
            raise AssertionError(f"QIL state '{row.get('state')}', expected '{expected}'.")

    def _assert_manager_todo_on_qil(self, ctx: dict) -> list[int]:
        assert self.admin is not None
        admin = self.admin
        log_id = ctx["quality_log_id"]
        manager_user_id = ctx["manager_user_id"]

        activity_ids = admin.search(
            "mail.activity",
            [
                ("res_model", "=", "quality.issue.log"),
                ("res_id", "=", log_id),
                ("user_id", "=", manager_user_id),
                ("summary", "=", ACTIVITY_SUMMARY),
            ],
        )
        if not activity_ids:
            raise AssertionError(
                "No To-Do mail.activity on quality.issue.log for manager after "
                f"ask_for_review (manager uid={manager_user_id}, "
                f"expected summary='{ACTIVITY_SUMMARY}')."
            )
        return activity_ids

    def _assert_no_approval_request(self, quality_log_id: int) -> None:
        """Document current gap: ask_for_review does not create approval.request."""
        assert self.admin is not None
        try:
            self.admin.fields_get("approval.request", attributes=["type"])
        except RpcError:
            return

        approval_ids = self._find_linked_approvals(quality_log_id)
        if approval_ids:
            raise AssertionError(
                "ask_for_review linked approval.request unexpectedly "
                f"(ids={approval_ids}). Current module should only create a QIL To-Do."
            )

    def _find_linked_approvals(self, quality_log_id: int) -> list[int]:
        assert self.admin is not None
        fg = self.admin.fields_get("approval.request", attributes=["type"])
        domains = []
        if "x_studio_quality_issue_log" in fg:
            domains.append([("x_studio_quality_issue_log", "=", quality_log_id)])
        if "quality_issue_log_id" in fg:
            domains.append([("quality_issue_log_id", "=", quality_log_id)])
        ids: list[int] = []
        for domain in domains:
            ids.extend(self.admin.search("approval.request", domain))
        return list(dict.fromkeys(ids))
