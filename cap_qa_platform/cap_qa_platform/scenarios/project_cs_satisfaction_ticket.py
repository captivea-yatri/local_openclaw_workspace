"""Scenario for testing customer satisfaction ticket creation and tracking in a project context."""
from __future__ import annotations

from datetime import date
from typing import Any

from cap_qa_platform.rpc.client import OdooRPCClient
from cap_qa_platform.scenarios.base import ScenarioRunResult, StepOutcome


class ProjectCsSatisfactionTicketScenario:
    SCENARIO_ID = "project_cs_satisfaction_ticket"

    def __init__(self, no_cleanup: bool = False, **kwargs):
        self.no_cleanup = no_cleanup
        # IDs of created records for cleanup
        self.project_id: int | None = None
        self.task_id: int | None = None
        self.timesheet_id: int | None = None
        self.ticket_id: int | None = None
        self.rating_id: int | None = None
        self.admin: OdooRPCClient | None = None  # store the admin RPC client

    def bind_admin(self, admin: OdooRPCClient) -> None:
        self.admin = admin

    def run(self, rpc: OdooRPCClient, role_name: str) -> ScenarioRunResult:
        result = ScenarioRunResult(scenario=self.SCENARIO_ID, role_name=role_name, success=False)
        try:
            # 1. Create a project
            project_vals = {
                "name": "Test Project for CS Ticket",
                # Optionally add a customer if needed
            }
            self.project_id = rpc.execute_kw("project.project", "create", [project_vals])

            # 2. Create a task in the project
            task_vals = {
                "name": "Test Task for CS Ticket",
                "project_id": self.project_id,
            }
            self.task_id = rpc.execute_kw("project.task", "create", [task_vals])

            # 3. Get the task's analytic account for timesheet
            task_data = rpc.execute_kw(
                "project.task",
                "read",
                [self.task_id],
                {"fields": ["account_id"]},
            )
            account_id = False
            if task_data and task_data[0].get("account_id"):
                account_id = task_data[0]["account_id"][0]  # (id, name)
            if not account_id:
                # Fallback: create an analytic account for the project
                analytic_vals = {
                    "name": f"Analytic for project {self.project_id}",
                }
                account_id = rpc.execute_kw("account.analytic.account", "create", [analytic_vals])

            # 4. Log time on the task
            today = date.today().isoformat()
            timesheet_vals = {
                "name": "Time spent on task",
                "unit_amount": 1.0,
                "date": today,
                "account_id": account_id,
                "task_id": self.task_id,
                "user_id": rpc.uid,  # current user (role)
            }
            self.timesheet_id = rpc.execute_kw("account.analytic.line", "create", [timesheet_vals])

            # 5. Create a helpdesk ticket linked to the task/project
            # Find a helpdesk team and ticket type (use first available)
            team_ids = rpc.execute_kw("helpdesk.team", "search", [[]], {"limit": 1})
            if not team_ids:
                raise Exception("No helpdesk team found. Please ensure the Helpdesk module is installed and configured.")
            team_id = team_ids[0]

            type_ids = rpc.execute_kw("helpdesk.ticket.type", "search", [[]], {"limit": 1})
            if not type_ids:
                raise Exception("No helpdesk ticket type found. Please ensure the Helpdesk module is installed and configured.")
            type_id = type_ids[0]

            ticket_vals = {
                "name": "Customer Satisfaction Ticket for Task",
                "description": "Ticket created to track customer satisfaction linked to project/task.",
                "project_id": self.project_id,
                "task_id": self.task_id,
                "team_id": team_id,
                "type_id": type_id,
            }
            self.ticket_id = rpc.execute_kw("helpdesk.ticket", "create", [ticket_vals])

            # 6. Move the ticket through stages: New -> In Progress -> Done -> Closed
            # Get stages for this ticket type, ordered by sequence
            stage_ids = rpc.execute_kw(
                "helpdesk.ticket.stage",
                "search",
                [("type_id", "=", type_id)],
                {"order": "sequence"},
            )
            if not stage_ids:
                raise Exception("No stages found for the ticket type.")
            # Map to expected stages; we'll use first four or fallback
            new_stage = stage_ids[0]
            in_progress_stage = stage_ids[1] if len(stage_ids) > 1 else new_stage
            done_stage = stage_ids[2] if len(stage_ids) > 2 else stage_ids[-1]
            closed_stage = stage_ids[3] if len(stage_ids) > 3 else stage_ids[-1]

            # Update ticket stage to In Progress
            rpc.execute_kw(
                "helpdesk.ticket",
                "write",
                [self.ticket_id],
                {"stage_id": in_progress_stage, "user_id": rpc.uid},
            )
            # Optionally verify
            ticket_data = rpc.execute_kw(
                "helpdesk.ticket",
                "read",
                [self.ticket_id],
                {"fields": ["stage_id"]},
            )
            assert ticket_data and ticket_data[0]["stage_id"][0] == in_progress_stage, "Failed to set stage to In Progress"

            # Update ticket stage to Done
            rpc.execute_kw(
                "helpdesk.ticket",
                "write",
                [self.ticket_id],
                {"stage_id": done_stage},
            )
            ticket_data = rpc.execute_kw(
                "helpdesk.ticket",
                "read",
                [self.ticket_id],
                {"fields": ["stage_id"]},
            )
            assert ticket_data and ticket_data[0]["stage_id"][0] == done_stage, "Failed to set stage to Done"

            # Update ticket stage to Closed
            rpc.execute_kw(
                "helpdesk.ticket",
                "write",
                [self.ticket_id],
                {"stage_id": closed_stage},
            )
            ticket_data = rpc.execute_kw(
                "helpdesk.ticket",
                "read",
                [self.ticket_id],
                {"fields": ["stage_id"]},
            )
            assert ticket_data and ticket_data[0]["stage_id"][0] == closed_stage, "Failed to set stage to Closed"

            # 7. Add a customer satisfaction rating to the ticket
            # Get the partner ID from the current user (or create a partner if needed)
            partner_id = False
            partner_data = rpc.execute_kw(
                "res.users",
                "read",
                [rpc.uid],
                {"fields": ["partner_id"]},
            )
            if partner_data and partner_data[0].get("partner_id"):
                partner_id = partner_data[0]["partner_id"][0]
            if not partner_id:
                # As a last resort, create a generic partner
                partner_vals = {
                    "name": "Test Customer",
                    "email": "test@example.com",
                }
                partner_id = rpc.execute_kw("res.partner", "create", [partner_vals])

            rating_vals = {
                "rating": 4,  # satisfaction rating 4/5
                "rated_partner_id": partner_id,
                "res_model": "helpdesk.ticket",
                "res_id": self.ticket_id,
                # survey_user_input_id can be left False for simple rating
            }
            self.rating_id = rpc.execute_kw("rating.rating", "create", [rating_vals])

            # Optionally verify the rating exists and is linked
            rating_data = rpc.execute_kw(
                "rating.rating",
                "read",
                [self.rating_id],
                {"fields": ["res_id", "rating"]},
            )
            assert rating_data and rating_data[0]["res_id"] == self.ticket_id and rating_data[0]["rating"] == 4, "Rating not set correctly"

            # If we reach here, all steps passed
            result.success = True
        except Exception as exc:
            result.failed_step = getattr(self, "_failed_step", "unknown")
            result.error = str(exc)
        return result

    def cleanup_as_admin(self, admin) -> None:
        if self.no_cleanup:
            return
        # We need to clean up the records we created.
        # We'll delete in reverse order to avoid foreign key issues.
        if self.rating_id:
            try:
                admin.unlink("rating.rating", [self.rating_id])
            except Exception:
                pass
        if self.ticket_id:
            try:
                admin.unlink("helpdesk.ticket", [self.ticket_id])
            except Exception:
                pass
        if self.timesheet_id:
            try:
                admin.unlink("account.analytic.line", [self.timesheet_id])
            except Exception:
                pass
        if self.task_id:
            try:
                admin.unlink("project.task", [self.task_id])
            except Exception:
                pass
        if self.project_id:
            try:
                admin.unlink("project.project", [self.project_id])
            except Exception:
                pass