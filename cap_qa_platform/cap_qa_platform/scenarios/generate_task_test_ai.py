"""Generate Task Test - AI (cap_project_ai) RPC scenario."""
from __future__ import annotations

from cap_qa_platform.rpc.client import OdooRPCClient, m2o_id
from cap_qa_platform.rpc.errors import RpcError
from cap_qa_platform.scenarios.base import ScenarioRunResult, StepOutcome
from cap_qa_platform.scenarios.so_base import _StepFailed, unique_suffix

SCENARIO_NAME = "generate_task_test_ai"
REQUIRED_MODULE = "cap_project_ai"
TASK_DESCRIPTION = """
<p><strong>Acceptance criteria</strong></p>
<ul>
  <li>User can save a project task when the required name field is filled.</li>
  <li>Task appears in the project task list with correct project link.</li>
  <li>Assigned user receives the task on their My Tasks view.</li>
  <li>Task description HTML is preserved after save and reload.</li>
</ul>
<p><strong>Technical notes</strong>: Models project.task, project.project; menu Project → Tasks.</p>
"""


class GenerateTaskTestAiScenario:
    SCENARIO_ID = SCENARIO_NAME

    def __init__(self, no_cleanup: bool = False, **kwargs):
        self.no_cleanup = no_cleanup
        self.admin: OdooRPCClient | None = None
        self.suffix = unique_suffix()
        self.cleanup_tracker: list[tuple[str, int]] = []
        self._ctx: dict = {}

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
            result.error = "Admin client required."
            return result
        try:
            self._step(result, "assert_module_installed", lambda: self._assert_module_installed())
            ctx = self._step(result, "setup_task", lambda: self._setup_task(rpc))
            self._step(
                result,
                "assert_description_set",
                lambda: self._assert_description_set(rpc, ctx["task_id"]),
            )
            before = self._step(
                result,
                "count_task_tests_before",
                lambda: self._count_task_tests(rpc, ctx["task_id"]),
            )
            wizard_id = self._step(
                result,
                "action_generate_tests",
                lambda: self._action_generate_tests(rpc, ctx["task_id"]),
            )
            line_count = self._step(
                result,
                "review_wizard_lines",
                lambda: self._review_wizard_lines(rpc, wizard_id),
            )
            self._step(
                result,
                "action_add_all_task_tests",
                lambda: self._action_add_all(rpc, wizard_id),
            )
            after = self._step(
                result,
                "assert_task_tests_created",
                lambda: self._assert_tests_created(rpc, ctx["task_id"], before, line_count),
            )
            result.records = {**ctx, "tests_before": before, "tests_after": after, "wizard_id": wizard_id}
            result.success = True
        except _StepFailed as exc:
            result.failed_step = exc.step
            result.error = exc.message
        return result

    def cleanup_as_admin(self, admin: OdooRPCClient) -> None:
        task_id = self._ctx.get("task_id")
        if task_id:
            test_ids = admin.search("test.test", [("task_id", "=", task_id)])
            if test_ids:
                try:
                    admin.unlink("test.test", test_ids)
                except RpcError:
                    pass
        for model, record_id in reversed(self.cleanup_tracker):
            try:
                admin.unlink(model, [record_id])
            except RpcError:
                pass
        self.cleanup_tracker.clear()
        self._ctx.clear()

    def _assert_module_installed(self) -> None:
        admin = self.admin
        assert admin is not None
        rows = admin.search_read(
            "ir.module.module",
            [("name", "=", REQUIRED_MODULE)],
            ["state"],
            limit=1,
        )
        if not rows or rows[0].get("state") != "installed":
            raise AssertionError(
                f"Module {REQUIRED_MODULE!r} is not installed on this database. "
                "Install cap_project_ai from staging before running this scenario."
            )

    def _setup_task(self, rpc: OdooRPCClient) -> dict:
        admin = self.admin
        assert admin is not None
        company_id = m2o_id(admin.read("res.users", [admin.uid], ["company_id"])[0]["company_id"])
        if not company_id:
            raise RpcError("Admin has no company_id.")

        project_id = admin.create(
            "project.project",
            {
                "name": f"CAPQA_AI_Tests_{self.suffix}",
                "company_id": company_id,
            },
        )
        self._track("project.project", project_id)

        task_id = admin.create(
            "project.task",
            {
                "name": f"CAPQA AI Task Test {self.suffix}",
                "project_id": project_id,
                "description": TASK_DESCRIPTION,
                "user_ids": [(4, rpc.uid)],
            },
        )
        self._track("project.task", task_id)
        self._ctx = {"project_id": project_id, "task_id": task_id}
        return self._ctx

    def _assert_description_set(self, rpc: OdooRPCClient, task_id: int) -> None:
        task = rpc.read("project.task", [task_id], ["description"])[0]
        if not (task.get("description") or "").strip():
            raise AssertionError("Task description must be set before generating AI task tests.")

    def _count_task_tests(self, rpc: OdooRPCClient, task_id: int) -> int:
        return rpc.search_count("test.test", [("task_id", "=", task_id)])

    def _action_generate_tests(self, rpc: OdooRPCClient, task_id: int) -> int:
        action = rpc.call("project.task", "action_generate_tests", [task_id])
        if not isinstance(action, dict):
            raise AssertionError(f"Unexpected action_generate_tests response: {action!r}")

        if action.get("type") == "ir.actions.client" and action.get("tag") == "display_notification":
            message = (action.get("params") or {}).get("message", "Unknown notification")
            raise AssertionError(f"Generate Task Test - AI failed: {message}")

        if action.get("res_model") != "task.test.ai.generation.wizard":
            raise AssertionError(f"Expected AI wizard action, got: {action!r}")

        wizard_id = action.get("res_id")
        if not wizard_id:
            raise AssertionError("Wizard action missing res_id.")
        return wizard_id

    def _review_wizard_lines(self, rpc: OdooRPCClient, wizard_id: int) -> int:
        wizard = rpc.read(
            "task.test.ai.generation.wizard",
            [wizard_id],
            ["task_test_lines_ai_generation_wizard_ids", "task_id"],
        )[0]
        line_ids = wizard.get("task_test_lines_ai_generation_wizard_ids") or []
        if not line_ids:
            raise AssertionError("AI wizard opened but contains no suggested task tests.")

        lines = rpc.read(
            "task.test.line.ai.generation.wizard",
            line_ids,
            ["name", "description"],
        )
        for line in lines:
            if not (line.get("name") or "").strip():
                raise AssertionError("Generated wizard line missing test name.")
        return len(lines)

    def _action_add_all(self, rpc: OdooRPCClient, wizard_id: int) -> None:
        rpc.call(
            "task.test.ai.generation.wizard",
            "action_add_task_tests",
            [wizard_id],
            context={"add_all_suggestions": True},
        )

    def _assert_tests_created(
        self,
        rpc: OdooRPCClient,
        task_id: int,
        before: int,
        expected_new: int,
    ) -> int:
        after = self._count_task_tests(rpc, task_id)
        created = after - before
        if created < 1:
            raise AssertionError(
                f"No task tests linked to task after Add All (before={before}, after={after})."
            )
        if created < expected_new:
            raise AssertionError(
                f"Expected at least {expected_new} new task tests, got {created} "
                f"(before={before}, after={after})."
            )
        tests = rpc.search_read(
            "test.test",
            [("task_id", "=", task_id)],
            ["name", "description", "task_id"],
            order="id desc",
            limit=3,
        )
        for test in tests:
            if not test.get("name"):
                raise AssertionError("Created test.test record missing name.")
            if m2o_id(test.get("task_id")) != task_id:
                raise AssertionError("Created test.test not linked to the task (Task Tests tab).")
        return after
