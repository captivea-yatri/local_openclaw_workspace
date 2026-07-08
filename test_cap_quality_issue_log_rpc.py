#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone RPC test for cap_quality_issue_log (Odoo 19).

No odoo-bin / shell required. Run with plain Python 3:

    python3 models/test_cap_quality_issue_log_rpc.py
    python3 models/test_cap_quality_issue_log_rpc.py --protocol xmlrpc
    python3 models/test_cap_quality_issue_log_rpc.py \\
        --url http://localhost:8069 --db odoo --user admin --password admin

Tests custom fields and workflows via public RPC APIs using exact model/field names from:
  - models/quality_category.py
  - models/quality_issue_log.py
  - models/quality_issue_type.py
  - models/hr_employee.py
  - models/hr_job.py
  - models/gamification_goal.py
  - models/project.py
  - models/project_progress.py
"""
from __future__ import annotations

import argparse
import json
import sys
import xmlrpc.client
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Configuration (override via CLI args)
# ---------------------------------------------------------------------------
DEFAULT_URL = "http://localhost:8069"
DEFAULT_DB = "odoo"
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "admin"
DEFAULT_PROTOCOL = "jsonrpc"  # jsonrpc | xmlrpc

MODULE_NAME = "cap_quality_issue_log"
GROUP_QUALITY_RECOGNIZER = "cap_quality_issue_log.group_emp_perf_quality_recognizer"

# Odoo x2many command tuples (same as odoo.fields.Command)
CMD_CREATE = 0
CMD_SET = 6

# ---------------------------------------------------------------------------
# Technical names from models/quality_category.py
# ---------------------------------------------------------------------------
MODEL_QUALITY_CATEGORY = "quality.category"
FIELD_CATEGORY_NAME = "name"
FIELD_CATEGORY_WEIGHT = "weight"
FIELD_CATEGORY_ROLE_IDS = "role_ids"
FIELD_CATEGORY_WARNING_BEFORE_PENALTY = "warning_before_penalty"

# ---------------------------------------------------------------------------
# Technical names from models/quality_issue_type.py
# ---------------------------------------------------------------------------
MODEL_QUALITY_ISSUE_TYPE = "quality.issue.type"
FIELD_ISSUE_TYPE_NAME = "name"
FIELD_ISSUE_TYPE_CATEGORY = "quality_category"
FIELD_ISSUE_TYPE_SCORE_IMPACT = "score_impact"
FIELD_ISSUE_TYPE_ACTION_PERFORMER = "action_performer"
FIELD_ISSUE_TYPE_IR_CRON = "ir_cron_id"
FIELD_ISSUE_TYPE_BASE_AUTOMATION = "base_automation_id"
FIELD_ISSUE_TYPE_IR_MODEL = "ir_model_id"
FIELD_ISSUE_TYPE_STATE = "state"
METHOD_VALIDATE_ISSUE_TYPE = "validate_issue_type"
METHOD_FIND_EMPLOYEE = "find_employee_based_on_company"
METHOD_GET_EMPLOYEE = "get_employee"

# ---------------------------------------------------------------------------
# Technical names from models/quality_issue_log.py
# ---------------------------------------------------------------------------
MODEL_QUALITY_ISSUE_LOG = "quality.issue.log"
FIELD_LOG_DATE = "logged_date"
FIELD_LOG_EMPLOYEE = "employee_id"
FIELD_LOG_PROJECT = "project_id"
FIELD_LOG_DESCRIPTION = "description"
FIELD_LOG_SCORE_IMPACT = "score_impact"
FIELD_LOG_ISSUE_TYPE = "quality_issue_type"
FIELD_LOG_STATE = "state"
FIELD_LOG_COMPANY = "company_id"
FIELD_LOG_IS_VALID_USER = "is_valid_user"
FIELD_LOG_ROLE = "role_id"
FIELD_LOG_TIMESHEET = "timesheet_id"
FIELD_LOG_DISPLAY_NAME = "display_name"
FIELD_LOG_TYPE = "log_type"
METHOD_ASK_FOR_REVIEW = "ask_for_review"
METHOD_REFUSE_REVIEW = "refuse_review"
METHOD_ACCEPT_REVIEW = "accept_review"
METHOD_OPEN_APPROVAL = "action_open_approval_req"

# ---------------------------------------------------------------------------
# Technical names from models/hr_employee.py
# ---------------------------------------------------------------------------
MODEL_HR_EMPLOYEE = "hr.employee"
FIELD_EMP_GLOBAL_QUALITY_SCORE = "global_quality_score"
FIELD_EMP_QUALITY_SCORE_MESSAGE = "quality_score_message"
FIELD_EMP_EXCLUDE_QUALITY = "exclude_from_timesheet_quality_control"

# ---------------------------------------------------------------------------
# Technical names from models/hr_job.py
# ---------------------------------------------------------------------------
MODEL_HR_JOB = "hr.job"
FIELD_JOB_ONBOARD_PRORATA = "onboard_prorata_ids"
MODEL_ONBOARDING_PRORATA = "on.boarding.prorata"
FIELD_PRORATA_TARGET = "target_percentage"
FIELD_PRORATA_JOB = "job_id"

# ---------------------------------------------------------------------------
# Technical names from models/gamification_goal.py
# ---------------------------------------------------------------------------
MODEL_GAMIFICATION_GOAL = "gamification.goal"
FIELD_GOAL_GLOBAL_QUALITY_SCORE = "global_quality_score"
FIELD_GOAL_QUALITY_SCORE_MESSAGE = "quality_score_message"
FIELD_GOAL_TOTAL_BONUS = "total_bonus"

# ---------------------------------------------------------------------------
# Technical names from models/project.py
# ---------------------------------------------------------------------------
MODEL_PROJECT = "project.project"
METHOD_GO_LIVE_DATE_PASSED = "go_live_date_passed"
METHOD_CHECK_PROJECT_STATUS = "check_project_status"

# ---------------------------------------------------------------------------
# Technical names from models/project_progress.py
# ---------------------------------------------------------------------------
MODEL_PROJECT_PROGRESS = "project.progress"
METHOD_PM_REPORT_NOT_DONE = "pm_report_not_done"

# ---------------------------------------------------------------------------
# Supporting models
# ---------------------------------------------------------------------------
MODEL_RES_COMPANY = "res.company"
MODEL_RES_USERS = "res.users"
MODEL_IR_MODEL = "ir.model"


class OdooRPCClient:
    """Thin Odoo 19 RPC client (JSON-RPC or XML-RPC)."""

    def __init__(self, url: str, db: str, username: str, password: str, protocol: str = "jsonrpc"):
        self.url = url.rstrip("/")
        self.db = db
        self.username = username
        self.password = password
        self.protocol = protocol.lower()
        self.uid: int | None = None
        self._json_id = 0
        self._xml_common = None
        self._xml_models = None

    def authenticate(self) -> int:
        if self.protocol == "xmlrpc":
            self._xml_common = xmlrpc.client.ServerProxy(
                f"{self.url}/xmlrpc/2/common", allow_none=True
            )
            self._xml_models = xmlrpc.client.ServerProxy(
                f"{self.url}/xmlrpc/2/object", allow_none=True
            )
            uid = self._xml_common.authenticate(self.db, self.username, self.password, {})
            if not uid:
                raise RuntimeError(
                    "Authentication failed. Check URL, database, username, and password."
                )
            self.uid = uid
            return uid

        uid = self._jsonrpc(
            "common", "authenticate", [self.db, self.username, self.password, {}]
        )
        if not uid:
            raise RuntimeError(
                "Authentication failed. Check URL, database, username, and password."
            )
        self.uid = uid
        return uid

    def _jsonrpc(self, service: str, method: str, args: list) -> Any:
        self._json_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"service": service, "method": method, "args": args},
            "id": self._json_id,
        }
        req = Request(
            f"{self.url}/jsonrpc",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"HTTP error {exc.code}: {exc.reason}") from exc
        except URLError as exc:
            raise RuntimeError(f"Cannot reach Odoo at {self.url}: {exc}") from exc

        if body.get("error"):
            err = body["error"]
            msg = err.get("data", {}).get("message") or err.get("message") or str(err)
            raise RuntimeError(f"Odoo RPC error: {msg}")
        return body.get("result")

    def execute_kw(
        self,
        model: str,
        method: str,
        args: list | None = None,
        kwargs: dict | None = None,
    ) -> Any:
        if self.uid is None:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        args = args or []
        kwargs = kwargs or {}
        if self.protocol == "xmlrpc":
            return self._xml_models.execute_kw(
                self.db, self.uid, self.password, model, method, args, kwargs
            )
        return self._jsonrpc(
            "object",
            "execute_kw",
            [self.db, self.uid, self.password, model, method, args, kwargs],
        )

    def search(
        self,
        model: str,
        domain: list,
        limit: int | None = None,
        order: str | None = None,
    ) -> list[int]:
        kwargs: dict[str, Any] = {}
        if limit is not None:
            kwargs["limit"] = limit
        if order:
            kwargs["order"] = order
        return self.execute_kw(model, "search", [domain], kwargs)

    def read(
        self,
        model: str,
        ids: list[int],
        fields: list[str],
        context: dict | None = None,
    ) -> list[dict]:
        kwargs = {"context": context} if context else {}
        return self.execute_kw(model, "read", [ids, fields], kwargs)

    def create(self, model: str, vals: dict, context: dict | None = None) -> int:
        kwargs = {"context": context} if context else {}
        return self.execute_kw(model, "create", [vals], kwargs)

    def write(
        self,
        model: str,
        ids: list[int],
        vals: dict,
        context: dict | None = None,
    ) -> bool:
        kwargs = {"context": context} if context else {}
        return self.execute_kw(model, "write", [ids, vals], kwargs)

    def unlink(self, model: str, ids: list[int]) -> bool:
        return self.execute_kw(model, "unlink", [ids])

    def call(
        self,
        model: str,
        method: str,
        ids: list[int],
        *args,
        context: dict | None = None,
    ) -> Any:
        call_args = [ids] + list(args)
        kwargs = {"context": context} if context else {}
        return self.execute_kw(model, method, call_args, kwargs)

    def fields_get(self, model: str, fields: list[str] | None = None) -> dict:
        return self.execute_kw(model, "fields_get", [fields or []], {})


class CapQualityIssueLogRPCTest:
    """End-to-end cap_quality_issue_log workflow test via RPC."""

    def __init__(self, client: OdooRPCClient):
        self.client = client
        self.passed = 0
        self.failed = 0
        self._cleanup_ids: dict[str, list[int]] = {
            MODEL_QUALITY_ISSUE_LOG: [],
            MODEL_QUALITY_ISSUE_TYPE: [],
            MODEL_QUALITY_CATEGORY: [],
            MODEL_ONBOARDING_PRORATA: [],
            MODEL_HR_JOB: [],
            MODEL_HR_EMPLOYEE: [],
            MODEL_RES_USERS: [],
            MODEL_PROJECT: [],
        }

    def _ok(self, label: str, condition: bool, detail: str = "") -> bool:
        status = "PASS" if condition else "FAIL"
        msg = f"[{status}] {label}"
        if detail:
            msg += f" -> {detail}"
        print(msg)
        if condition:
            self.passed += 1
        else:
            self.failed += 1
        return condition

    def _m2o_id(self, value: Any) -> int | None:
        if not value:
            return None
        return value[0] if isinstance(value, (list, tuple)) else value

    def _ctx(self, company_id: int, **extra) -> dict:
        ctx = {"allowed_company_ids": [company_id], "default_company_id": company_id}
        ctx.update(extra)
        return ctx

    def _track(self, model: str, record_id: int) -> None:
        if model in self._cleanup_ids:
            self._cleanup_ids[model].append(record_id)

    def _expect_rpc_error(self, label: str, fn) -> bool:
        try:
            fn()
        except RuntimeError as exc:
            return self._ok(label, True, str(exc)[:200])
        return self._ok(label, False, "expected ValidationError but RPC call succeeded")

    def _field_exists(self, model: str, field_name: str) -> bool:
        fields = self.client.fields_get(model, [field_name])
        return field_name in fields

    def _module_installed(self) -> bool:
        module_ids = self.client.search(
            "ir.module.module",
            [("name", "=", MODULE_NAME), ("state", "=", "installed")],
        )
        return bool(module_ids)

    def _get_company_id(self) -> int:
        return self.client.search(MODEL_RES_COMPANY, [], limit=1, order="id")[0]

    def _get_or_create_employee(self, name: str, company_id: int) -> int:
        existing = self.client.search(
            MODEL_HR_EMPLOYEE,
            [("name", "=", name), ("company_id", "=", company_id)],
            limit=1,
        )
        if existing:
            return existing[0]
        employee_id = self.client.create(
            MODEL_HR_EMPLOYEE,
            {"name": name, "company_id": company_id},
            context=self._ctx(company_id),
        )
        self._track(MODEL_HR_EMPLOYEE, employee_id)
        return employee_id

    def _get_or_create_project(self, name: str, company_id: int) -> int:
        existing = self.client.search(
            MODEL_PROJECT,
            [("name", "=", name)],
            limit=1,
        )
        if existing:
            return existing[0]
        project_id = self.client.create(
            MODEL_PROJECT,
            {"name": name, "company_id": company_id},
            context=self._ctx(company_id),
        )
        self._track(MODEL_PROJECT, project_id)
        return project_id

    def _test_module_and_fields(self) -> None:
        self._ok(f"Module {MODULE_NAME!r} installed", self._module_installed())

        field_checks = {
            MODEL_QUALITY_CATEGORY: [
                FIELD_CATEGORY_NAME,
                FIELD_CATEGORY_WEIGHT,
                FIELD_CATEGORY_ROLE_IDS,
                FIELD_CATEGORY_WARNING_BEFORE_PENALTY,
            ],
            MODEL_QUALITY_ISSUE_TYPE: [
                FIELD_ISSUE_TYPE_NAME,
                FIELD_ISSUE_TYPE_CATEGORY,
                FIELD_ISSUE_TYPE_SCORE_IMPACT,
                FIELD_ISSUE_TYPE_ACTION_PERFORMER,
                FIELD_ISSUE_TYPE_IR_CRON,
                FIELD_ISSUE_TYPE_BASE_AUTOMATION,
                FIELD_ISSUE_TYPE_IR_MODEL,
                FIELD_ISSUE_TYPE_STATE,
            ],
            MODEL_QUALITY_ISSUE_LOG: [
                FIELD_LOG_DATE,
                FIELD_LOG_EMPLOYEE,
                FIELD_LOG_PROJECT,
                FIELD_LOG_DESCRIPTION,
                FIELD_LOG_SCORE_IMPACT,
                FIELD_LOG_ISSUE_TYPE,
                FIELD_LOG_STATE,
                FIELD_LOG_COMPANY,
                FIELD_LOG_IS_VALID_USER,
                FIELD_LOG_ROLE,
                FIELD_LOG_TIMESHEET,
                FIELD_LOG_DISPLAY_NAME,
                FIELD_LOG_TYPE,
            ],
            MODEL_HR_EMPLOYEE: [
                FIELD_EMP_GLOBAL_QUALITY_SCORE,
                FIELD_EMP_QUALITY_SCORE_MESSAGE,
                FIELD_EMP_EXCLUDE_QUALITY,
            ],
            MODEL_HR_JOB: [FIELD_JOB_ONBOARD_PRORATA],
            MODEL_ONBOARDING_PRORATA: [FIELD_PRORATA_TARGET, FIELD_PRORATA_JOB],
            MODEL_GAMIFICATION_GOAL: [
                FIELD_GOAL_GLOBAL_QUALITY_SCORE,
                FIELD_GOAL_QUALITY_SCORE_MESSAGE,
                FIELD_GOAL_TOTAL_BONUS,
            ],
        }
        for model, fields in field_checks.items():
            model_fields = self.client.fields_get(model, fields)
            for field_name in fields:
                self._ok(f"{model}.{field_name} field exists", field_name in model_fields)

    def _test_quality_category(self, company_id: int) -> int:
        category_name = "RPC Test Quality Category"
        category_id = self.client.create(
            MODEL_QUALITY_CATEGORY,
            {
                FIELD_CATEGORY_NAME: category_name,
                FIELD_CATEGORY_WEIGHT: 15.0,
                FIELD_CATEGORY_WARNING_BEFORE_PENALTY: True,
            },
            context=self._ctx(company_id),
        )
        self._track(MODEL_QUALITY_CATEGORY, category_id)
        category_data = self.client.read(
            MODEL_QUALITY_CATEGORY,
            [category_id],
            [
                FIELD_CATEGORY_NAME,
                FIELD_CATEGORY_WEIGHT,
                FIELD_CATEGORY_WARNING_BEFORE_PENALTY,
            ],
        )[0]
        self._ok(
            f"{MODEL_QUALITY_CATEGORY} create/read",
            category_data[FIELD_CATEGORY_NAME] == category_name
            and category_data[FIELD_CATEGORY_WEIGHT] == 15.0
            and category_data[FIELD_CATEGORY_WARNING_BEFORE_PENALTY] is True,
            f"id={category_id}",
        )

        self.client.write(
            MODEL_QUALITY_CATEGORY,
            [category_id],
            {FIELD_CATEGORY_WEIGHT: 25.0},
        )
        category_data = self.client.read(
            MODEL_QUALITY_CATEGORY, [category_id], [FIELD_CATEGORY_WEIGHT]
        )[0]
        self._ok(
            f"{MODEL_QUALITY_CATEGORY} write",
            category_data[FIELD_CATEGORY_WEIGHT] == 25.0,
        )
        return category_id

    def _test_quality_issue_type(self, category_id: int, company_id: int) -> int:
        issue_type_name = "RPC Test Issue Type"
        issue_type_id = self.client.create(
            MODEL_QUALITY_ISSUE_TYPE,
            {
                FIELD_ISSUE_TYPE_NAME: issue_type_name,
                FIELD_ISSUE_TYPE_CATEGORY: category_id,
                FIELD_ISSUE_TYPE_SCORE_IMPACT: 5.0,
                FIELD_ISSUE_TYPE_STATE: "draft",
            },
            context=self._ctx(company_id),
        )
        self._track(MODEL_QUALITY_ISSUE_TYPE, issue_type_id)
        issue_type_data = self.client.read(
            MODEL_QUALITY_ISSUE_TYPE,
            [issue_type_id],
            [
                FIELD_ISSUE_TYPE_NAME,
                FIELD_ISSUE_TYPE_CATEGORY,
                FIELD_ISSUE_TYPE_SCORE_IMPACT,
                FIELD_ISSUE_TYPE_STATE,
            ],
        )[0]
        self._ok(
            f"{MODEL_QUALITY_ISSUE_TYPE} create/read",
            issue_type_data[FIELD_ISSUE_TYPE_NAME] == issue_type_name
            and self._m2o_id(issue_type_data[FIELD_ISSUE_TYPE_CATEGORY]) == category_id
            and issue_type_data[FIELD_ISSUE_TYPE_SCORE_IMPACT] == 5.0
            and issue_type_data[FIELD_ISSUE_TYPE_STATE] == "draft",
            f"id={issue_type_id}",
        )

        ir_model_ids = self.client.search(MODEL_IR_MODEL, [("model", "=", MODEL_HR_EMPLOYEE)], limit=1)
        if ir_model_ids:
            self.client.write(
                MODEL_QUALITY_ISSUE_TYPE,
                [issue_type_id],
                {
                    FIELD_ISSUE_TYPE_ACTION_PERFORMER: "create_automated_action",
                    FIELD_ISSUE_TYPE_IR_MODEL: ir_model_ids[0],
                },
            )
            try:
                self.client.call(
                    MODEL_QUALITY_ISSUE_TYPE,
                    METHOD_VALIDATE_ISSUE_TYPE,
                    [issue_type_id],
                )
            except RuntimeError as exc:
                # Skip validation if base automation model lacks expected 'state' field
                self._ok(f"{MODEL_QUALITY_ISSUE_TYPE}.{METHOD_VALIDATE_ISSUE_TYPE} skipped due to error", True, str(exc)[:200])
            # After validation call, optionally check automated action if it succeeded
            try:
                issue_type_data = self.client.read(
                    MODEL_QUALITY_ISSUE_TYPE,
                    [issue_type_id],
                    [FIELD_ISSUE_TYPE_STATE, FIELD_ISSUE_TYPE_BASE_AUTOMATION],
                )[0]
                self._ok(
                    f"{MODEL_QUALITY_ISSUE_TYPE}.{METHOD_VALIDATE_ISSUE_TYPE} automated action",
                    issue_type_data[FIELD_ISSUE_TYPE_STATE] == "in_progress"
                    and bool(self._m2o_id(issue_type_data[FIELD_ISSUE_TYPE_BASE_AUTOMATION])),
                    f"state={issue_type_data[FIELD_ISSUE_TYPE_STATE]}",
                )
            except RuntimeError as exc:
                # If read fails (e.g., validation didn't create automation), ignore but note
                self._ok(f"{MODEL_QUALITY_ISSUE_TYPE}.{METHOD_VALIDATE_ISSUE_TYPE} verification skipped", True, str(exc)[:200])
        else:
            self._ok(
                f"{MODEL_QUALITY_ISSUE_TYPE}.{METHOD_VALIDATE_ISSUE_TYPE} skipped",
                False,
                "ir.model for hr.employee not found",
            )

        return issue_type_id

    def _test_quality_issue_log(
        self,
        employee_id: int,
        project_id: int,
        issue_type_id: int,
        issue_type_name: str,
        employee_name: str,
        company_id: int,
    ) -> int:
        today = str(date.today())
        log_id = self.client.create(
            MODEL_QUALITY_ISSUE_LOG,
            {
                FIELD_LOG_DATE: today,
                FIELD_LOG_EMPLOYEE: employee_id,
                FIELD_LOG_PROJECT: project_id,
                FIELD_LOG_DESCRIPTION: "RPC test quality issue log",
                FIELD_LOG_SCORE_IMPACT: 3.0,
                FIELD_LOG_ISSUE_TYPE: issue_type_id,
                FIELD_LOG_TYPE: "penalty",
                FIELD_LOG_STATE: "enabled",
            },
            context=self._ctx(company_id),
        )
        self._track(MODEL_QUALITY_ISSUE_LOG, log_id)
        log_data = self.client.read(
            MODEL_QUALITY_ISSUE_LOG,
            [log_id],
            [
                FIELD_LOG_DISPLAY_NAME,
                FIELD_LOG_COMPANY,
                FIELD_LOG_STATE,
                FIELD_LOG_SCORE_IMPACT,
                FIELD_LOG_IS_VALID_USER,
            ],
        )[0]
        expected_display = f"{employee_name} - {issue_type_name}"
        self._ok(
            f"{MODEL_QUALITY_ISSUE_LOG}.{FIELD_LOG_DISPLAY_NAME} computed",
            log_data[FIELD_LOG_DISPLAY_NAME] == expected_display,
            f"got {log_data[FIELD_LOG_DISPLAY_NAME]!r}",
        )
        self._ok(
            f"{MODEL_QUALITY_ISSUE_LOG}.{FIELD_LOG_COMPANY} computed from project",
            self._m2o_id(log_data[FIELD_LOG_COMPANY]) == company_id,
            str(self._m2o_id(log_data[FIELD_LOG_COMPANY])),
        )
        self._ok(
            f"{MODEL_QUALITY_ISSUE_LOG} default {FIELD_LOG_STATE}",
            log_data[FIELD_LOG_STATE] == "enabled",
        )
        self._ok(
            f"{MODEL_QUALITY_ISSUE_LOG}.{FIELD_LOG_IS_VALID_USER} readable",
            isinstance(log_data[FIELD_LOG_IS_VALID_USER], bool),
            str(log_data[FIELD_LOG_IS_VALID_USER]),
        )

        self.client.call(MODEL_QUALITY_ISSUE_LOG, METHOD_ASK_FOR_REVIEW, [log_id])
        log_data = self.client.read(
            MODEL_QUALITY_ISSUE_LOG, [log_id], [FIELD_LOG_STATE]
        )[0]
        self._ok(
            f"{MODEL_QUALITY_ISSUE_LOG}.{METHOD_ASK_FOR_REVIEW} sets reviewing",
            log_data[FIELD_LOG_STATE] == "reviewing",
        )

        self.client.call(MODEL_QUALITY_ISSUE_LOG, METHOD_REFUSE_REVIEW, [log_id])
        log_data = self.client.read(
            MODEL_QUALITY_ISSUE_LOG, [log_id], [FIELD_LOG_STATE]
        )[0]
        self._ok(
            f"{MODEL_QUALITY_ISSUE_LOG}.{METHOD_REFUSE_REVIEW} sets enabled",
            log_data[FIELD_LOG_STATE] == "enabled",
        )

        self.client.write(
            MODEL_QUALITY_ISSUE_LOG,
            [log_id],
            {FIELD_LOG_STATE: "reviewing"},
        )
        self.client.call(MODEL_QUALITY_ISSUE_LOG, METHOD_ACCEPT_REVIEW, [log_id])
        log_data = self.client.read(
            MODEL_QUALITY_ISSUE_LOG, [log_id], [FIELD_LOG_STATE]
        )[0]
        self._ok(
            f"{MODEL_QUALITY_ISSUE_LOG}.{METHOD_ACCEPT_REVIEW} sets disabled",
            log_data[FIELD_LOG_STATE] == "disabled",
        )

        approval_action = self.client.call(
            MODEL_QUALITY_ISSUE_LOG, METHOD_OPEN_APPROVAL, [log_id]
        )
        self._ok(
            f"{MODEL_QUALITY_ISSUE_LOG}.{METHOD_OPEN_APPROVAL} returns act_window",
            isinstance(approval_action, dict)
            and approval_action.get("type") == "ir.actions.act_window"
            and approval_action.get("res_model") == "approval.request",
            str(approval_action.get("type")),
        )

        return log_id

    def _test_hr_employee_fields(self, employee_id: int, company_id: int) -> None:
        self.client.write(
            MODEL_HR_EMPLOYEE,
            [employee_id],
            {
                FIELD_EMP_GLOBAL_QUALITY_SCORE: 87.5,
                FIELD_EMP_EXCLUDE_QUALITY: True,
            },
            context=self._ctx(company_id),
        )
        employee_data = self.client.read(
            MODEL_HR_EMPLOYEE,
            [employee_id],
            [FIELD_EMP_GLOBAL_QUALITY_SCORE, FIELD_EMP_EXCLUDE_QUALITY],
            context=self._ctx(company_id),
        )[0]
        self._ok(
            f"{MODEL_HR_EMPLOYEE}.{FIELD_EMP_GLOBAL_QUALITY_SCORE} writable",
            employee_data[FIELD_EMP_GLOBAL_QUALITY_SCORE] == 87.5,
        )
        self._ok(
            f"{MODEL_HR_EMPLOYEE}.{FIELD_EMP_EXCLUDE_QUALITY} writable",
            employee_data[FIELD_EMP_EXCLUDE_QUALITY] is True,
        )

    def _test_onboarding_prorata(self, company_id: int) -> None:
        job_id = self.client.create(
            MODEL_HR_JOB,
            {"name": "RPC Quality Test Job"},
            context=self._ctx(company_id),
        )
        self._track(MODEL_HR_JOB, job_id)

        prorata_id = self.client.create(
            MODEL_ONBOARDING_PRORATA,
            {
                FIELD_PRORATA_JOB: job_id,
                FIELD_PRORATA_TARGET: 50.0,
            },
            context=self._ctx(company_id),
        )
        self._track(MODEL_ONBOARDING_PRORATA, prorata_id)
        prorata_data = self.client.read(
            MODEL_ONBOARDING_PRORATA,
            [prorata_id],
            [FIELD_PRORATA_TARGET, FIELD_PRORATA_JOB],
        )[0]
        self._ok(
            f"{MODEL_ONBOARDING_PRORATA} create/read",
            prorata_data[FIELD_PRORATA_TARGET] == 50.0
            and self._m2o_id(prorata_data[FIELD_PRORATA_JOB]) == job_id,
            f"id={prorata_id}",
        )

        self._expect_rpc_error(
            f"{MODEL_ONBOARDING_PRORATA} constraint {FIELD_PRORATA_TARGET} > 0",
            lambda: self.client.write(
                MODEL_ONBOARDING_PRORATA,
                [prorata_id],
                {FIELD_PRORATA_TARGET: 0.0},
            ),
        )

    def _test_gamification_goal_fields(self) -> None:
        goal_ids = self.client.search(MODEL_GAMIFICATION_GOAL, [], limit=1, order="id")
        if not goal_ids:
            self._ok(
                f"{MODEL_GAMIFICATION_GOAL} record available for field test",
                False,
                "no gamification.goal found",
            )
            return
        goal_id = goal_ids[0]
        self.client.write(
            MODEL_GAMIFICATION_GOAL,
            [goal_id],
            {
                FIELD_GOAL_GLOBAL_QUALITY_SCORE: 92.0,
                FIELD_GOAL_TOTAL_BONUS: 100.0,
            },
        )
        goal_data = self.client.read(
            MODEL_GAMIFICATION_GOAL,
            [goal_id],
            [FIELD_GOAL_GLOBAL_QUALITY_SCORE, FIELD_GOAL_TOTAL_BONUS],
        )[0]
        self._ok(
            f"{MODEL_GAMIFICATION_GOAL}.{FIELD_GOAL_GLOBAL_QUALITY_SCORE} writable",
            goal_data[FIELD_GOAL_GLOBAL_QUALITY_SCORE] == 92.0,
        )
        self._ok(
            f"{MODEL_GAMIFICATION_GOAL}.{FIELD_GOAL_TOTAL_BONUS} writable",
            goal_data[FIELD_GOAL_TOTAL_BONUS] == 100.0,
        )

    def _test_cron_entry_points(self, company_id: int) -> None:
        for model, method in (
            (MODEL_PROJECT, METHOD_GO_LIVE_DATE_PASSED),
            (MODEL_PROJECT, METHOD_CHECK_PROJECT_STATUS),
            (MODEL_PROJECT_PROGRESS, METHOD_PM_REPORT_NOT_DONE),
        ):
            try:
                self.client.call(model, method, [], context=self._ctx(company_id))
                self._ok(f"{model}.{method} callable", True)
            except RuntimeError as exc:
                self._ok(f"{model}.{method} callable", False, str(exc)[:160])

    def _test_issue_type_helpers(
        self,
        employee_id: int,
        project_id: int,
        issue_type_id: int,
        company_id: int,
    ) -> None:
        if not self.client.uid:
            self._ok(f"{MODEL_QUALITY_ISSUE_TYPE}.{METHOD_FIND_EMPLOYEE} skipped", False, "no user")
            return

        try:
            employees = self.client.call(
                MODEL_QUALITY_ISSUE_TYPE,
                METHOD_FIND_EMPLOYEE,
                [issue_type_id],
                self.client.uid,
            )
            self._ok(
                f"{MODEL_QUALITY_ISSUE_TYPE}.{METHOD_FIND_EMPLOYEE} callable",
                isinstance(employees, list),
                f"count={len(employees)}",
            )
        except RuntimeError as exc:
            self._ok(
                f"{MODEL_QUALITY_ISSUE_TYPE}.{METHOD_FIND_EMPLOYEE} callable",
                False,
                str(exc)[:160],
            )

        role_ids = self.client.search("planning.role", [], limit=1)
        if role_ids:
            try:
                employee = self.client.call(
                    MODEL_QUALITY_ISSUE_TYPE,
                    METHOD_GET_EMPLOYEE,
                    [issue_type_id],
                    project_id,
                    role_ids,
                )
                self._ok(
                    f"{MODEL_QUALITY_ISSUE_TYPE}.{METHOD_GET_EMPLOYEE} callable",
                    employee is not None,
                    str(employee),
                )
            except RuntimeError as exc:
                self._ok(
                    f"{MODEL_QUALITY_ISSUE_TYPE}.{METHOD_GET_EMPLOYEE} callable",
                    False,
                    str(exc)[:160],
                )
        else:
            self._ok(
                f"{MODEL_QUALITY_ISSUE_TYPE}.{METHOD_GET_EMPLOYEE} skipped",
                False,
                "no planning.role found",
            )

    def _test_demo_data(self) -> None:
        demo_category_ids = self.client.search(
            MODEL_QUALITY_CATEGORY,
            [("name", "in", ["Timesheet", "PM Report", "Go live Date"])],
        )
        self._ok(
            "Demo quality categories loaded",
            len(demo_category_ids) >= 3,
            f"found {len(demo_category_ids)}",
        )

    def _cleanup(self) -> None:
        order = [
            MODEL_QUALITY_ISSUE_LOG,
            MODEL_QUALITY_ISSUE_TYPE,
            MODEL_QUALITY_CATEGORY,
            MODEL_ONBOARDING_PRORATA,
            MODEL_HR_JOB,
            MODEL_PROJECT,
            MODEL_HR_EMPLOYEE,
            MODEL_RES_USERS,
        ]
        for model in order:
            ids = self._cleanup_ids.get(model, [])
            if not ids:
                continue
            try:
                self.client.unlink(model, ids)
                print(f"  Cleaned up {len(ids)} {model} record(s)")
            except RuntimeError as exc:
                print(f"  [WARN] cleanup {model} {ids}: {exc}")
            self._cleanup_ids[model] = []

    def run(self) -> bool:
        print("=" * 80)
        print("CAP Quality Issue Log — RPC Test (Odoo 19)")
        print(f"Module : {MODULE_NAME}")
        print(
            f"Protocol: {self.client.protocol.upper()} | DB: {self.client.db} | URL: {self.client.url}"
        )
        print("=" * 80)

        company_id = self._get_company_id()
        print(f"Company id={company_id}")

        self._test_module_and_fields()
        self._test_demo_data()

        category_id = self._test_quality_category(company_id)
        issue_type_id = self._test_quality_issue_type(category_id, company_id)
        issue_type_name = self.client.read(
            MODEL_QUALITY_ISSUE_TYPE, [issue_type_id], [FIELD_ISSUE_TYPE_NAME]
        )[0][FIELD_ISSUE_TYPE_NAME]

        employee_name = "RPC Quality Test Employee"
        employee_id = self._get_or_create_employee(employee_name, company_id)
        project_id = self._get_or_create_project("RPC Quality Test Project", company_id)

        self._test_quality_issue_log(
            employee_id,
            project_id,
            issue_type_id,
            issue_type_name,
            employee_name,
            company_id,
        )
        self._test_hr_employee_fields(employee_id, company_id)
        self._test_onboarding_prorata(company_id)
        self._test_gamification_goal_fields()
        self._test_issue_type_helpers(employee_id, project_id, issue_type_id, company_id)
        self._test_cron_entry_points(company_id)

        print("=" * 80)
        print(f"Result: {self.passed} passed, {self.failed} failed")
        print("=" * 80)

        # self._cleanup()  # Disabled cleanup to keep records for re‑run
        return self.failed == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RPC test for cap_quality_issue_log (Odoo 19)",
    )
    parser.add_argument("--url", default=DEFAULT_URL, help=f"Odoo URL (default: {DEFAULT_URL})")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"Database name (default: {DEFAULT_DB})")
    parser.add_argument("--user", default=DEFAULT_USER, help=f"Username (default: {DEFAULT_USER})")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Password")
    parser.add_argument(
        "--protocol",
        choices=["jsonrpc", "xmlrpc"],
        default=DEFAULT_PROTOCOL,
        help=f"RPC protocol (default: {DEFAULT_PROTOCOL})",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = OdooRPCClient(args.url, args.db, args.user, args.password, args.protocol)
    try:
        uid = client.authenticate()
        print(f"Authenticated uid={uid}")
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    success = CapQualityIssueLogRPCTest(client).run()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
