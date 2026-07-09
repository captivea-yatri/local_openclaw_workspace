"""Project create → auto Customer Success Satisfaction helpdesk ticket (ksc_project_extended)."""
from __future__ import annotations

from cap_qa_platform.rpc.client import OdooRPCClient, m2o_id
from cap_qa_platform.rpc.errors import RpcError
from cap_qa_platform.scenarios.base import ScenarioRunResult, StepOutcome
from cap_qa_platform.scenarios.so_base import _StepFailed, unique_suffix

SCENARIO_ID = "project_cs_satisfaction_ticket"
CS_TEAM_NAME = "Customer Success Satisfaction"
REQUIRED_MODULES = ("ksc_project_extended", "helpdesk", "project")


class ProjectCsSatisfactionTicketScenario:
    SCENARIO_ID = SCENARIO_ID

    def __init__(self, no_cleanup: bool = False, **kwargs):
        self.no_cleanup = no_cleanup
        self.admin: OdooRPCClient | None = None
        self.suffix = unique_suffix()
        self.company_id: int | None = None
        self.cs_team_id: int | None = None
        self.original_csm_id: int | False = False
        self.partner_id: int | None = None
        self.cleanup_tracker: list[tuple[str, int]] = []

    def bind_admin(self, admin: OdooRPCClient) -> None:
        self.admin = admin

    def _track(self, model: str, record_id: int) -> None:
        if not self.no_cleanup and record_id:
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
        result = ScenarioRunResult(scenario=self.SCENARIO_ID, role_name=role_name, success=False)
        if not self.admin:
            result.failed_step = "setup"
            result.error = "Admin client required (bind_admin)."
            return result
        try:
            self._step(result, "assert_modules_installed", lambda: self._assert_modules(rpc))
            self._step(result, "assert_feature_fields", lambda: self._assert_feature_fields())
            ctx = self._step(result, "resolve_cs_team", lambda: self._resolve_cs_team())
            self.company_id = ctx["company_id"]
            self.cs_team_id = ctx["cs_team_id"]
            self.original_csm_id = ctx["original_csm_id"]
            csm_user_id = ctx["csm_user_id"]
            team_member_ids = ctx["team_member_ids"]
            self.partner_id = self._step(
                result,
                "create_test_customer",
                lambda: self._create_test_customer(),
            )

            project_a = self._step(
                result,
                "create_project_with_company_csm",
                lambda: self._create_project_with_csm(rpc, csm_user_id),
            )
            ticket_a = self._step(
                result,
                "assert_ticket_linked_and_assigned_to_csm",
                lambda: self._assert_project_ticket(
                    project_a,
                    expected_user_id=csm_user_id,
                    path_label="company CSM",
                ),
            )

            project_b = self._step(
                result,
                "create_project_without_company_csm",
                lambda: self._create_project_without_csm(rpc),
            )
            ticket_b = self._step(
                result,
                "assert_ticket_assigned_to_team_member",
                lambda: self._assert_project_ticket(
                    project_b,
                    expected_user_ids=team_member_ids,
                    path_label="helpdesk team member fallback",
                ),
            )

            result.records = {
                "company_id": self.company_id,
                "partner_id": self.partner_id,
                "cs_team_id": self.cs_team_id,
                "csm_user_id": csm_user_id,
                "team_member_ids": team_member_ids,
                "project_with_csm_id": project_a,
                "ticket_with_csm_id": ticket_a,
                "project_fallback_id": project_b,
                "ticket_fallback_id": ticket_b,
            }
            result.success = True
        except _StepFailed as exc:
            result.failed_step = exc.step
            result.error = exc.message
        return result

    def cleanup_as_admin(self, admin: OdooRPCClient) -> None:
        if self.no_cleanup:
            return
        for model, record_id in reversed(self.cleanup_tracker):
            try:
                admin.unlink(model, [record_id])
            except RpcError:
                pass
        self.cleanup_tracker.clear()
        if self.company_id is not None:
            try:
                admin.write(
                    "res.company",
                    [self.company_id],
                    {"cust_success_manager_id": self.original_csm_id or False},
                )
            except RpcError:
                pass

    def _assert_modules(self, rpc: OdooRPCClient) -> None:
        missing = [
            module
            for module in REQUIRED_MODULES
            if not rpc.search_count(
                "ir.module.module",
                [("name", "=", module), ("state", "=", "installed")],
            )
        ]
        if missing:
            raise RpcError(f"Missing installed modules: {', '.join(missing)}")

    def _assert_feature_fields(self) -> None:
        admin = self.admin
        assert admin is not None
        for model, field in (
            ("project.project", "cs_ticket_id"),
            ("res.company", "cust_success_manager_id"),
        ):
            fields = admin.fields_get(model, [field])
            if field not in fields:
                raise RpcError(f"Expected field {model}.{field} is not available.")

    def _resolve_cs_team(self) -> dict:
        admin = self.admin
        assert admin is not None
        company_id = m2o_id(admin.read("res.users", [admin.uid], ["company_id"])[0]["company_id"])
        if not company_id:
            raise RpcError("Admin user has no company_id.")

        teams = admin.search_read(
            "helpdesk.team",
            [("name", "ilike", CS_TEAM_NAME)],
            ["id", "name", "member_ids"],
            limit=1,
        )
        if not teams:
            raise RpcError(f'Helpdesk team "{CS_TEAM_NAME}" not found.')
        team = teams[0]
        member_ids = team.get("member_ids") or []
        if not member_ids:
            raise RpcError(f'Helpdesk team "{team["name"]}" has no member_ids configured.')

        company = admin.read("res.company", [company_id], ["cust_success_manager_id"])[0]
        original_csm_id = m2o_id(company.get("cust_success_manager_id")) or False
        csm_user_id = member_ids[0]

        return {
            "company_id": company_id,
            "cs_team_id": team["id"],
            "cs_team_name": team["name"],
            "team_member_ids": member_ids,
            "original_csm_id": original_csm_id,
            "csm_user_id": csm_user_id,
        }

    def _create_test_customer(self) -> int:
        admin = self.admin
        assert admin is not None and self.company_id is not None
        partner_id = admin.create(
            "res.partner",
            {
                "name": f"CAPQA_CS_PARTNER_{self.suffix}",
                "is_company": True,
                "company_id": self.company_id,
            },
        )
        self._track("res.partner", partner_id)
        return partner_id

    def _create_project_with_csm(self, _rpc: OdooRPCClient, csm_user_id: int) -> int:
        return self._create_project(csm_user_id=csm_user_id, label="CSM")

    def _create_project_without_csm(self, _rpc: OdooRPCClient) -> int:
        return self._create_project(csm_user_id=False, label="FALLBACK")

    def _create_project(self, *, csm_user_id: int | bool, label: str) -> int:
        admin = self.admin
        assert admin is not None and self.company_id is not None
        admin.write(
            "res.company",
            [self.company_id],
            {"cust_success_manager_id": csm_user_id or False},
        )
        project_id = admin.create(
            "project.project",
            {
                "name": f"CAPQA_CS_{label}_{self.suffix}",
                "company_id": self.company_id,
                "partner_id": self.partner_id,
            },
        )
        self._track("project.project", project_id)
        return project_id

    def _assert_project_ticket(
        self,
        project_id: int,
        *,
        expected_user_id: int | None = None,
        expected_user_ids: list[int] | None = None,
        path_label: str,
    ) -> int:
        admin = self.admin
        assert admin is not None and self.cs_team_id is not None
        project = admin.read("project.project", [project_id], ["cs_ticket_id"])[0]
        ticket_ref = project.get("cs_ticket_id")
        if not ticket_ref:
            raise RpcError(
                f"No cs_ticket_id linked on project {project_id} ({path_label}). "
                "Expected automatic CS ticket creation on project create."
            )
        ticket_id = m2o_id(ticket_ref)
        self._track("helpdesk.ticket", ticket_id)

        ticket = admin.read(
            "helpdesk.ticket",
            [ticket_id],
            ["name", "team_id", "user_id"],
        )[0]
        team_id = m2o_id(ticket.get("team_id"))
        assignee_id = m2o_id(ticket.get("user_id"))

        if team_id != self.cs_team_id:
            raise RpcError(
                f"Ticket {ticket_id} team_id={team_id} != expected CS team "
                f"{self.cs_team_id} ({path_label})."
            )
        if expected_user_id is not None and assignee_id != expected_user_id:
            raise RpcError(
                f"Ticket {ticket_id} assignee user_id={assignee_id} != expected "
                f"company CSM {expected_user_id} ({path_label})."
            )
        if expected_user_ids is not None:
            if not assignee_id:
                raise RpcError(
                    f"Ticket {ticket_id} has no assignee; expected helpdesk team member "
                    f"fallback ({path_label})."
                )
            if assignee_id not in expected_user_ids:
                raise RpcError(
                    f"Ticket {ticket_id} assignee user_id={assignee_id} not in helpdesk "
                    f"team members {expected_user_ids} ({path_label})."
                )
        return ticket_id
