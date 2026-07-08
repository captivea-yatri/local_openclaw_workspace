"""Quality issue ask for review scenario."""
from __future__ import annotations

from datetime import date

from cap_qa_platform.rpc.client import OdooRPCClient, m2o_id
from cap_qa_platform.rpc.errors import RpcError
from cap_qa_platform.scenarios.base import ScenarioRunResult, StepOutcome
from cap_qa_platform.scenarios.so_base import _StepFailed, unique_suffix

SCENARIO_NAME = "quality_issue_ask_for_review"
ACTIVITY_SUMMARY = "Review Quality Issue"


class QualityIssueAskForReviewScenario:
    def __init__(self, no_cleanup: bool = False, **kwargs):
        self.no_cleanup = no_cleanup
        self.admin = None
        self.suffix = unique_suffix()
        self.cleanup_tracker: list[tuple[str, int]] = []

    def bind_admin(self, admin) -> None:
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
            result.error = "Admin client required."
            return result
        try:
            ctx = self._step(result, "setup_quality_log", lambda: self._setup(rpc))
            self._step(
                result,
                "ask_for_review",
                lambda: rpc.call("quality.issue.log", "ask_for_review", [ctx["quality_log_id"]]),
            )
            self._step(
                result,
                "assert_state_reviewing",
                lambda: self._assert_state(rpc, ctx["quality_log_id"], "reviewing"),
            )
            self._step(
                result,
                "assert_manager_todo_on_qil",
                lambda: self._assert_manager_todo(ctx),
            )
            result.records = ctx
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

    def _setup(self, rpc: OdooRPCClient) -> dict:
        admin = self.admin
        company_id = m2o_id(admin.read("res.users", [admin.uid], ["company_id"])[0]["company_id"])
        manager_login = f"capqa_mgr_{self.suffix}@test.local"
        manager_ids = admin.search("res.users", [("login", "=", manager_login)], limit=1)
        manager_user_id = manager_ids[0] if manager_ids else admin.create(
            "res.users",
            {
                "name": f"CAP QA Manager {self.suffix}",
                "login": manager_login,
                "password": "cap_qa_test",
                "company_id": company_id,
                "company_ids": [(6, 0, [company_id])],
            },
        )
        if not manager_ids:
            self._track("res.users", manager_user_id)
        manager_emp_ids = admin.search("hr.employee", [("user_id", "=", manager_user_id)], limit=1)
        manager_employee_id = manager_emp_ids[0] if manager_emp_ids else admin.create(
            "hr.employee",
            {"name": f"CAP QA Manager {self.suffix}", "user_id": manager_user_id, "company_id": company_id},
        )
        if not manager_emp_ids:
            self._track("hr.employee", manager_employee_id)
        emp_ids = admin.search("hr.employee", [("user_id", "=", rpc.uid)], limit=1)
        if emp_ids:
            employee_id = emp_ids[0]
            admin.write("hr.employee", [employee_id], {"parent_id": manager_employee_id})
        else:
            employee_id = admin.create(
                "hr.employee",
                {
                    "name": f"CAP QA Employee {self.suffix}",
                    "user_id": rpc.uid,
                    "company_id": company_id,
                    "parent_id": manager_employee_id,
                },
            )
            self._track("hr.employee", employee_id)
        issue_types = admin.search_read("quality.issue.type", [], ["id", "score_impact"], limit=1)
        if issue_types:
            issue_type_id = issue_types[0]["id"]
            score = issue_types[0].get("score_impact") or 5.0
        else:
            issue_type_id = admin.create(
                "quality.issue.type",
                {"name": f"CAP QA Type {self.suffix}", "score_impact": 5.0, "state": "in_progress"},
            )
            self._track("quality.issue.type", issue_type_id)
            score = 5.0
        quality_log_id = admin.create(
            "quality.issue.log",
            {
                "logged_date": date.today().isoformat(),
                "employee_id": employee_id,
                "description": f"CAP QA QIL {self.suffix}",
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
        }

    def _assert_state(self, rpc, quality_log_id: int, expected: str) -> None:
        row = rpc.read("quality.issue.log", [quality_log_id], ["state"])[0]
        if row.get("state") != expected:
            raise AssertionError(f"QIL state '{row.get('state')}', expected '{expected}'.")

    def _assert_manager_todo(self, ctx: dict) -> None:
        admin = self.admin
        activity_ids = admin.search(
            "mail.activity",
            [
                ("res_model", "=", "quality.issue.log"),
                ("res_id", "=", ctx["quality_log_id"]),
                ("user_id", "=", ctx["manager_user_id"]),
                ("summary", "=", ACTIVITY_SUMMARY),
            ],
        )
        if not activity_ids:
            raise AssertionError("No manager To-Do on quality.issue.log after ask_for_review.")
