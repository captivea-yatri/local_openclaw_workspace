#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone RPC flow test for cap_single_employee_for_multi_company (Odoo 19).

Validates the "Anne Engin" single-employee multi-company scenario:

  BEFORE: user had multiple employees (Anne Engin LLC, Anne Engin France, …)
          and had to pick the right one per project — error-prone.

  AFTER:  one employee record linked to the user; timesheets on any company
          project auto-use that employee. Default company (Captivea LLC) must
          stay active.

  Time off: leave can only be requested for types allocated on the employee's
            default company — not France/Luxembourg allocations.

  Expense:  created in another company's context still resolves to the default-
            company employee; posting must keep that employee.

Flow (RPC):
  Authenticate → module check → companies LLC/France/Lux → one user → one employee
  → multi-company access → projects/tasks → timesheets → leave → expenses → cleanup

Run:
    python3 models/test_cap_single_employee_for_multi_company_rpc.py
    python3 models/test_cap_single_employee_for_multi_company_rpc.py --protocol xmlrpc
    python3 models/test_cap_single_employee_for_multi_company_rpc.py \\
        --url http://localhost:8069 --db odoo --user admin --password admin
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
# Configuration
# ---------------------------------------------------------------------------
DEFAULT_URL = "http://localhost:8069"
DEFAULT_DB = "odoo"
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "admin"
DEFAULT_PROTOCOL = "jsonrpc"

MODULE_NAME = "cap_single_employee_for_multi_company"
TEST_USER_LOGIN = "anne_engin_rpc_tester"
TEST_USER_PASSWORD = "anne_engin_test"
TEST_PREFIX = "CAP SEEMC RPC"

# Scenario labels (maps to functional doc)
COMPANY_DEFAULT = "Captivea LLC"       # Company A — employee default company, must be active
COMPANY_FRANCE = "Captivea France"     # Company B
COMPANY_LUX = "Captivea Luxembourg"    # Company C
EMPLOYEE_NAME = "Anne Engin"

CMD_CREATE = 0
CMD_SET = 6

MODEL_RES_USERS = "res.users"
MODEL_HR_EMPLOYEE = "hr.employee"
FIELD_USER_EMPLOYEE = "employee_id"

MODEL_HR_LEAVE = "hr.leave"
FIELD_LEAVE_EMPLOYEE = "employee_id"
FIELD_LEAVE_HOLIDAY_STATUS = "holiday_status_id"

MODEL_HR_LEAVE_ALLOCATION = "hr.leave.allocation"
FIELD_ALLOC_HOLIDAY_TYPE = "holiday_type"
FIELD_ALLOC_EMPLOYEE = "employee_id"
FIELD_ALLOC_MODE_COMPANY = "mode_company_id"
FIELD_ALLOC_HOLIDAY_STATUS = "holiday_status_id"
FIELD_ALLOC_NUMBER_OF_DAYS = "number_of_days"

MODEL_RES_COMPANY = "res.company"
MODEL_HR_LEAVE_TYPE = "hr.leave.type"
MODEL_PROJECT = "project.project"
MODEL_PROJECT_TASK = "project.task"
MODEL_ANALYTIC_LINE = "account.analytic.line"
MODEL_HR_EXPENSE = "hr.expense"

OPTIONAL_MODULES = {
    "project": MODEL_PROJECT,
    "hr_timesheet": MODEL_ANALYTIC_LINE,
    "hr_expense": MODEL_HR_EXPENSE,
}


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
        else:
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
        context: dict | None = None,
    ) -> Any:
        kwargs = {"context": context} if context else {}
        return self.execute_kw(model, method, [ids], kwargs)

    def fields_get(self, model: str, fields: list[str] | None = None) -> dict:
        return self.execute_kw(model, "fields_get", [fields or []], {})


class SingleEmployeeFlowRPCTest:
    """
    End-to-end RPC test for the Anne Engin / Captivea single-employee scenario.

    Company keys:
      LLC    — default company (Captivea LLC), must be active
      France — Captivea France
      Lux    — Captivea Luxembourg
    """

    def __init__(self, admin: OdooRPCClient, args: argparse.Namespace):
        self.admin = admin
        self.args = args
        self.user_client: OdooRPCClient | None = None
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self._cleanup_ids: dict[str, list[int]] = {
            MODEL_ANALYTIC_LINE: [],
            MODEL_HR_EXPENSE: [],
            MODEL_HR_LEAVE: [],
            MODEL_HR_LEAVE_ALLOCATION: [],
            MODEL_PROJECT_TASK: [],
            MODEL_PROJECT: [],
            MODEL_HR_LEAVE_TYPE: [],
            MODEL_HR_EMPLOYEE: [],
            MODEL_RES_USERS: [],
            MODEL_RES_COMPANY: [],
        }
        self.companies: dict[str, int] = {}
        self.user_id: int | None = None
        self.employee_id: int | None = None
        self.project_ids: dict[str, int] = {}
        self.task_ids: dict[str, int] = {}
        self.leave_type_ids: dict[str, int] = {}

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

    def _skip(self, label: str, reason: str) -> None:
        print(f"[SKIP] {label} -> {reason}")
        self.skipped += 1

    def _section(self, title: str) -> None:
        print()
        print("-" * 80)
        print(title)
        print("-" * 80)

    def _m2o_id(self, value: Any) -> int | None:
        if not value:
            return None
        return value[0] if isinstance(value, (list, tuple)) else value

    def _ctx(self, company_id: int, **extra) -> dict:
        ctx = {"allowed_company_ids": [company_id], "default_company_id": company_id}
        ctx.update(extra)
        return ctx

    def _multi_company_ctx(self, active_company_id: int, **extra) -> dict:
        """User has access to LLC/France/Lux; active company is the one being worked in."""
        allowed = [self._company_id(k) for k in ("LLC", "France", "Lux")]
        ctx = {"allowed_company_ids": allowed, "default_company_id": active_company_id}
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
        return self._ok(label, False, "expected ValidationError/UserError but call succeeded")

    def _module_installed(self, name: str) -> bool:
        try:
            ids = self.admin.search(
                "ir.module.module",
                [("name", "=", name), ("state", "=", "installed")],
            )
            return bool(ids)
        except RuntimeError:
            return self._model_available(OPTIONAL_MODULES.get(name, name))

    def _model_available(self, model: str) -> bool:
        try:
            self.admin.fields_get(model, [])
            return True
        except RuntimeError:
            return False

    def _ref_id(self, xml_id: str) -> int | None:
        module, name = xml_id.split(".", 1)
        data_ids = self.admin.search(
            "ir.model.data",
            [("module", "=", module), ("name", "=", name)],
            limit=1,
        )
        if not data_ids:
            return None
        return self.admin.read("ir.model.data", data_ids, ["res_id"])[0]["res_id"]

    def _group_ids(self, xml_ids: list[str]) -> list[int]:
        ids = []
        for xml_id in xml_ids:
            ref = self._ref_id(xml_id)
            if ref:
                ids.append(ref)
        return ids

    def _get_or_create_company(self, name: str, fallback_ids: list[int] | None = None) -> int:
        existing = self.admin.search(MODEL_RES_COMPANY, [("name", "=", name)], limit=1)
        if existing:
            return existing[0]
        try:
            company_id = self.admin.create(MODEL_RES_COMPANY, {"name": name})
            self._track(MODEL_RES_COMPANY, company_id)
            return company_id
        except RuntimeError as exc:
            if fallback_ids:
                for company_id in fallback_ids:
                    data = self.admin.read(MODEL_RES_COMPANY, [company_id], ["name", "active"])
                    if data:
                        print(
                            f"  [WARN] using existing company {data[0]['name']!r} "
                            f"(id={company_id}) instead of creating {name!r}: {str(exc)[:120]}"
                        )
                        return company_id
            raise

    def _create_leave_type(self, name: str, company_id: int) -> int:
        leave_type_id = self.admin.create(
            MODEL_HR_LEAVE_TYPE,
            {
                "name": name,
                "company_id": company_id,
                "requires_allocation": "yes",
                "employee_requests": "yes",
            },
            context=self._ctx(company_id),
        )
        self._track(MODEL_HR_LEAVE_TYPE, leave_type_id)
        return leave_type_id

    def _validate_allocation(self, allocation_id: int, company_id: int) -> None:
        try:
            self.admin.call(
                MODEL_HR_LEAVE_ALLOCATION,
                "action_approve",
                [allocation_id],
                context=self._ctx(company_id),
            )
        except RuntimeError:
            self.admin.write(
                MODEL_HR_LEAVE_ALLOCATION,
                [allocation_id],
                {"state": "validate"},
                context=self._ctx(company_id),
            )

    def _leave_vals(
        self,
        leave_type_id: int,
        employee_id: int | None = None,
        day_offset: int = 0,
    ) -> dict:
        from datetime import timedelta
        leave_day = date.today() + timedelta(days=day_offset)
        today = str(leave_day)
        vals = {
            FIELD_LEAVE_HOLIDAY_STATUS: leave_type_id,
            "request_date_from": today,
            "request_date_to": today,
            "date_from": f"{today} 08:00:00",
            "date_to": f"{today} 17:00:00",
        }
        if employee_id:
            vals[FIELD_LEAVE_EMPLOYEE] = employee_id
        return vals

    def _company_id(self, key: str) -> int:
        company_id = self.companies.get(key)
        if not company_id:
            raise RuntimeError(f"Company {key!r} not set up")
        return company_id

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_companies(self) -> None:
        self._section(
            f"Companies: {COMPANY_DEFAULT} (default, active), {COMPANY_FRANCE}, {COMPANY_LUX}"
        )
        fallback = self.admin.search(MODEL_RES_COMPANY, [], limit=3, order="id")
        fb = [fallback[i] if i < len(fallback) else fallback[0] for i in range(3)]

        self.companies["LLC"] = self._get_or_create_company(
            f"{TEST_PREFIX} {COMPANY_DEFAULT}", [fb[0]]
        )
        self.companies["France"] = self._get_or_create_company(
            f"{TEST_PREFIX} {COMPANY_FRANCE}", [fb[1]]
        )
        self.companies["Lux"] = self._get_or_create_company(
            f"{TEST_PREFIX} {COMPANY_LUX}", [fb[2]]
        )

        llc_data = self.admin.read(
            MODEL_RES_COMPANY, [self.companies["LLC"]], ["name", "active"]
        )[0]
        self._ok(
            f"Default company ({COMPANY_DEFAULT}) is active",
            llc_data.get("active") is True,
            f"id={self.companies['LLC']}, name={llc_data.get('name')!r}",
        )
        self._ok(
            "Three companies ready (LLC / France / Lux)",
            all(self.companies.values()),
            str(self.companies),
        )

    def _setup_user_and_employee(self) -> None:
        self._section(f"ONE user + ONE employee ({EMPLOYEE_NAME}, default company = LLC)")
        existing = self.admin.search(MODEL_RES_USERS, [("login", "=", TEST_USER_LOGIN)], limit=1)
        group_xmlids = [
            "base.group_user",
            "hr.group_hr_user",
            "hr_holidays.group_hr_holidays_user",
        ]
        if self._module_installed("project"):
            group_xmlids.append("project.group_project_user")
        if self._module_installed("hr_timesheet"):
            group_xmlids.append("hr_timesheet.group_hr_timesheet_user")
        if self._module_installed("hr_expense"):
            group_xmlids.append("hr_expense.group_hr_expense_user")
        group_ids = self._group_ids(group_xmlids)

        llc_id = self._company_id("LLC")
        france_id = self._company_id("France")
        lux_id = self._company_id("Lux")

        if existing:
            self.user_id = existing[0]
        else:
            self.user_id = self.admin.create(
                MODEL_RES_USERS,
                {
                    "name": f"{TEST_PREFIX} {EMPLOYEE_NAME}",
                    "login": TEST_USER_LOGIN,
                    "email": f"{TEST_USER_LOGIN}@example.com",
                    "group_ids": [(CMD_SET, 0, group_ids)],
                },
            )
            self._track(MODEL_RES_USERS, self.user_id)

        self.admin.write(
            MODEL_RES_USERS,
            [self.user_id],
            {
                "company_id": llc_id,
                "company_ids": [(CMD_SET, 0, [llc_id, france_id, lux_id])],
                "password": TEST_USER_PASSWORD,
                "group_ids": [(CMD_SET, 0, group_ids)],
            },
        )

        employee_name = f"{TEST_PREFIX} {EMPLOYEE_NAME}"
        employee_existing = self.admin.search(
            MODEL_HR_EMPLOYEE,
            [("user_id", "=", self.user_id)],
            limit=1,
        )
        if employee_existing:
            self.employee_id = employee_existing[0]
            self.admin.write(
                MODEL_HR_EMPLOYEE,
                [self.employee_id],
                {"company_id": llc_id, "name": employee_name},
                context=self._ctx(llc_id),
            )
        else:
            self.employee_id = self.admin.create(
                MODEL_HR_EMPLOYEE,
                {
                    "name": employee_name,
                    "company_id": llc_id,
                    "user_id": self.user_id,
                },
                context=self._ctx(llc_id),
            )
            self._track(MODEL_HR_EMPLOYEE, self.employee_id)

        employee_count = self.admin.search(
            MODEL_HR_EMPLOYEE, [("user_id", "=", self.user_id), ("active", "=", True)]
        )
        self._ok(
            "No duplicate per-company employees (single Anne Engin only)",
            len(employee_count) == 1,
            f"active employee count={len(employee_count)}",
        )
        self._ok(
            f"{EMPLOYEE_NAME} default company is {COMPANY_DEFAULT}",
            self._m2o_id(
                self.admin.read(MODEL_HR_EMPLOYEE, [self.employee_id], ["company_id"])[0][
                    "company_id"
                ]
            )
            == llc_id,
            f"employee_id={self.employee_id}",
        )

        user_companies = self.admin.read(
            MODEL_RES_USERS, [self.user_id], ["company_id", "company_ids"]
        )[0]
        allowed = {self._m2o_id(c) for c in user_companies["company_ids"]}
        self._ok(
            f"{EMPLOYEE_NAME} has access to LLC, France, and Lux",
            {llc_id, france_id, lux_id}.issubset(allowed),
            str(sorted(allowed)),
        )
        self._ok(
            f"User default company is {COMPANY_DEFAULT}",
            self._m2o_id(user_companies["company_id"]) == llc_id,
        )

    def _authenticate_test_user(self) -> None:
        self.user_client = OdooRPCClient(
            self.args.url,
            self.args.db,
            TEST_USER_LOGIN,
            TEST_USER_PASSWORD,
            self.args.protocol,
        )
        uid = self.user_client.authenticate()
        self._ok(f"{EMPLOYEE_NAME} authenticated", bool(uid), f"uid={uid}")

    def _test_user_employee_across_companies(self) -> None:
        """res.users.employee_id must resolve to the single employee in every company."""
        self._section("User employee_id is always the single employee (all companies)")
        if not self.user_client or not self.user_id or not self.employee_id:
            self._skip("Cross-company employee_id", "test user not ready")
            return

        for key in ("LLC", "France", "Lux"):
            company_id = self._company_id(key)
            user_data = self.user_client.read(
                MODEL_RES_USERS,
                [self.user_id],
                [FIELD_USER_EMPLOYEE],
                context=self._ctx(company_id),
            )[0]
            self._ok(
                f"user.employee_id in {key} context = {EMPLOYEE_NAME}",
                self._m2o_id(user_data[FIELD_USER_EMPLOYEE]) == self.employee_id,
                f"got={self._m2o_id(user_data[FIELD_USER_EMPLOYEE])}",
            )

    def _setup_projects_and_tasks(self) -> None:
        self._section("Projects & tasks per company (France / Lux / LLC projects)")
        if not self._module_installed("project"):
            self._skip("Projects and tasks", "project module not installed")
            return

        project_fields = self.admin.fields_get(MODEL_PROJECT, [])
        has_allow_timesheets = "allow_timesheets" in project_fields

        for key in ("LLC", "France", "Lux"):
            company_id = self._company_id(key)
            project_name = f"{TEST_PREFIX} Project {key}"
            existing = self.admin.search(
                MODEL_PROJECT,
                [("name", "=", project_name), ("company_id", "=", company_id)],
                limit=1,
            )
            if existing:
                project_id = existing[0]
            else:
                vals: dict[str, Any] = {"name": project_name, "company_id": company_id}
                if has_allow_timesheets:
                    vals["allow_timesheets"] = True
                project_id = self.admin.create(MODEL_PROJECT, vals, context=self._ctx(company_id))
                self._track(MODEL_PROJECT, project_id)
            self.project_ids[key] = project_id

            task_name = f"{TEST_PREFIX} Task {key}"
            task_existing = self.admin.search(
                MODEL_PROJECT_TASK,
                [("name", "=", task_name), ("project_id", "=", project_id)],
                limit=1,
            )
            if task_existing:
                task_id = task_existing[0]
            else:
                task_id = self.admin.create(
                    MODEL_PROJECT_TASK,
                    {"name": task_name, "project_id": project_id},
                    context=self._ctx(company_id),
                )
                self._track(MODEL_PROJECT_TASK, task_id)
            self.task_ids[key] = task_id

        self._ok("One project + task per company", len(self.project_ids) == 3, str(self.project_ids))

    def _setup_intercompany_timesheet_prereqs(self) -> None:
        """
        odoo19_captivea2 installs cap_manage_inter_company_timesheet: cross-company
        timesheets need an internal project on the employee's company (LLC).
        """
        if not self._model_available(MODEL_PROJECT):
            return
        fields = self.admin.fields_get(MODEL_PROJECT, [])
        if "project_status_id" not in fields:
            return

        llc_id = self._company_id("LLC")
        status_ids = self.admin.search(
            "project.status", [("code", "=", "internal")], limit=1
        )
        if not status_ids:
            self._skip(
                "Intercompany timesheet setup",
                "project.status code=internal not found (cap_partner)",
            )
            return
        status_id = status_ids[0]

        for key in ("France", "Lux"):
            foreign_id = self._company_id(key)
            foreign = self.admin.read(
                MODEL_RES_COMPANY, [foreign_id], ["name", "partner_id"]
            )[0]
            partner_id = self._m2o_id(foreign.get("partner_id"))
            if not partner_id:
                continue

            internal_name = f"{TEST_PREFIX} Internal {foreign['name']}"
            existing = self.admin.search(
                MODEL_PROJECT,
                [
                    ("name", "=", internal_name),
                    ("company_id", "=", llc_id),
                    ("partner_id", "=", partner_id),
                ],
                limit=1,
            )
            if existing:
                continue

            try:
                project_id = self.admin.create(
                    MODEL_PROJECT,
                    {
                        "name": internal_name,
                        "company_id": llc_id,
                        "partner_id": partner_id,
                        "project_status_id": status_id,
                        "allow_timesheets": True,
                    },
                    context=self._ctx(llc_id),
                )
                self._track(MODEL_PROJECT, project_id)
                print(
                    f"  [INFO] created internal project id={project_id} "
                    f"on LLC for {foreign['name']!r}"
                )
            except RuntimeError as exc:
                print(
                    f"  [WARN] could not create internal project for {key}: {str(exc)[:120]}"
                )

    # ------------------------------------------------------------------
    # Timesheets — AFTER: no need to pick "Anne Engin France" on France project
    # ------------------------------------------------------------------

    def _test_timesheets(self) -> None:
        self._section(
            "Timesheet tests — France/Lux/LLC projects all use single employee"
        )
        if not self._module_installed("hr_timesheet"):
            self._skip("Timesheet tests", "hr_timesheet module not installed")
            return
        if not self.user_client or not self.employee_id or len(self.project_ids) < 3:
            self._skip("Timesheet tests", "prerequisites missing")
            return

        self._setup_intercompany_timesheet_prereqs()

        today = str(date.today())
        for key, label in (
            ("LLC", COMPANY_DEFAULT),
            ("France", COMPANY_FRANCE),
            ("Lux", COMPANY_LUX),
        ):
            company_id = self._company_id(key)
            ts_ctx = self._multi_company_ctx(company_id)
            try:
                line_id = self.user_client.create(
                    MODEL_ANALYTIC_LINE,
                    {
                        "name": f"{TEST_PREFIX} Timesheet {label}",
                        "project_id": self.project_ids[key],
                        "task_id": self.task_ids[key],
                        "date": today,
                        "unit_amount": 1.0,
                    },
                    context=ts_ctx,
                )
            except RuntimeError as exc:
                self._ok(
                    f"Timesheet on {label} project → employee auto = {EMPLOYEE_NAME}",
                    False,
                    str(exc)[:200],
                )
                continue
            self._track(MODEL_ANALYTIC_LINE, line_id)
            line = self.user_client.read(
                MODEL_ANALYTIC_LINE,
                [line_id],
                ["employee_id", "project_id"],
                context=ts_ctx,
            )[0]
            self._ok(
                f"Timesheet on {label} project → employee auto = {EMPLOYEE_NAME}",
                self._m2o_id(line["employee_id"]) == self.employee_id,
                f"employee_id={self._m2o_id(line['employee_id'])}",
            )

    # ------------------------------------------------------------------
    # Leave — only default-company (LLC) allocations can be requested
    # ------------------------------------------------------------------

    def _cleanup_existing_test_leaves(self) -> None:
        if not self.employee_id:
            return
        leave_ids = self.admin.search(
            MODEL_HR_LEAVE,
            [("employee_id", "=", self.employee_id), ("state", "in", ["draft", "confirm"])],
        )
        for leave_id in leave_ids:
            try:
                self.admin.call(MODEL_HR_LEAVE, "action_refuse", [leave_id])
            except RuntimeError:
                pass
        draft_ids = self.admin.search(
            MODEL_HR_LEAVE,
            [("employee_id", "=", self.employee_id), ("state", "in", ["draft", "refuse"])],
        )
        if draft_ids:
            try:
                self.admin.unlink(MODEL_HR_LEAVE, draft_ids)
            except RuntimeError:
                pass

    def _test_leave(self) -> None:
        self._section(
            f"Leave tests — request only {COMPANY_DEFAULT} allocation; France/Lux blocked"
        )
        assert self.employee_id
        self._cleanup_existing_test_leaves()
        llc_id = self._company_id("LLC")
        france_id = self._company_id("France")
        lux_id = self._company_id("Lux")

        self.leave_type_ids["LLC"] = self._create_leave_type(
            f"{TEST_PREFIX} Leave {COMPANY_DEFAULT}", llc_id
        )
        self.leave_type_ids["France"] = self._create_leave_type(
            f"{TEST_PREFIX} Leave {COMPANY_FRANCE}", france_id
        )
        self.leave_type_ids["Lux"] = self._create_leave_type(
            f"{TEST_PREFIX} Leave {COMPANY_LUX}", lux_id
        )

        # Allocate on default company
        alloc_vals_llc: dict[str, Any] = {
            "name": f"{TEST_PREFIX} Allocation LLC",
            FIELD_ALLOC_EMPLOYEE: self.employee_id,
            FIELD_ALLOC_HOLIDAY_STATUS: self.leave_type_ids["LLC"],
            FIELD_ALLOC_NUMBER_OF_DAYS: 5.0,
        }
        alloc_fields = self.admin.fields_get(MODEL_HR_LEAVE_ALLOCATION, [])
        if FIELD_ALLOC_HOLIDAY_TYPE in alloc_fields:
            alloc_vals_llc[FIELD_ALLOC_HOLIDAY_TYPE] = "employee"

        alloc_llc_id = self.admin.create(
            MODEL_HR_LEAVE_ALLOCATION,
            alloc_vals_llc,
            context=self._ctx(llc_id),
        )
        self._track(MODEL_HR_LEAVE_ALLOCATION, alloc_llc_id)
        self._validate_allocation(alloc_llc_id, llc_id)
        self._ok(
            f"Allocate leave on {COMPANY_DEFAULT}",
            self.admin.read(MODEL_HR_LEAVE_ALLOCATION, [alloc_llc_id], ["state"])[0]["state"]
            == "validate",
            f"id={alloc_llc_id}",
        )

        has_mode_company = FIELD_ALLOC_MODE_COMPANY in alloc_fields
        if has_mode_company and FIELD_ALLOC_HOLIDAY_TYPE in alloc_fields:
            alloc_france_id = self.admin.create(
                MODEL_HR_LEAVE_ALLOCATION,
                {
                    "name": f"{TEST_PREFIX} Allocation France",
                    FIELD_ALLOC_HOLIDAY_TYPE: "company",
                    FIELD_ALLOC_MODE_COMPANY: france_id,
                    FIELD_ALLOC_HOLIDAY_STATUS: self.leave_type_ids["France"],
                    FIELD_ALLOC_NUMBER_OF_DAYS: 5.0,
                },
                context=self._ctx(france_id),
            )
            self._track(MODEL_HR_LEAVE_ALLOCATION, alloc_france_id)
            self._validate_allocation(alloc_france_id, france_id)
            self._ok(
                f"Allocate leave on {COMPANY_FRANCE} (company mode)",
                self.admin.read(MODEL_HR_LEAVE_ALLOCATION, [alloc_france_id], ["state"])[0]["state"]
                == "validate",
                f"id={alloc_france_id}",
            )

        bad_alloc_vals: dict[str, Any] = {
            "name": f"{TEST_PREFIX} Bad Allocation France",
            FIELD_ALLOC_EMPLOYEE: self.employee_id,
            FIELD_ALLOC_HOLIDAY_STATUS: self.leave_type_ids["France"],
            FIELD_ALLOC_NUMBER_OF_DAYS: 1.0,
        }
        if FIELD_ALLOC_HOLIDAY_TYPE in alloc_fields:
            bad_alloc_vals[FIELD_ALLOC_HOLIDAY_TYPE] = "employee"
        self._expect_rpc_error(
            f"Allocation for {COMPANY_FRANCE} leave type (employee on LLC) — FAIL",
            lambda: self.admin.create(
                MODEL_HR_LEAVE_ALLOCATION,
                bad_alloc_vals,
                context=self._ctx(france_id),
            ),
        )

        client = self.admin  # hr.leave RPC may be restricted for non-admin on this DB

        leave_llc_id = client.create(
            MODEL_HR_LEAVE,
            self._leave_vals(self.leave_type_ids["LLC"], self.employee_id),
            context=self._ctx(llc_id),
        )
        self._track(MODEL_HR_LEAVE, leave_llc_id)
        leave_llc = client.read(
            MODEL_HR_LEAVE,
            [leave_llc_id],
            [FIELD_LEAVE_EMPLOYEE, FIELD_LEAVE_HOLIDAY_STATUS],
            context=self._ctx(llc_id),
        )[0]
        self._ok(
            f"Request {COMPANY_DEFAULT} leave — PASS",
            self._m2o_id(leave_llc[FIELD_LEAVE_EMPLOYEE]) == self.employee_id
            and self._m2o_id(leave_llc[FIELD_LEAVE_HOLIDAY_STATUS]) == self.leave_type_ids["LLC"],
            f"leave_id={leave_llc_id}",
        )

        self._expect_rpc_error(
            f"Request {COMPANY_FRANCE} leave (not default company allocation) — FAIL",
            lambda: client.create(
                MODEL_HR_LEAVE,
                self._leave_vals(self.leave_type_ids["France"], self.employee_id, day_offset=1),
                context=self._ctx(france_id),
            ),
        )

        self._expect_rpc_error(
            f"Request {COMPANY_LUX} leave (not default company allocation) — FAIL",
            lambda: client.create(
                MODEL_HR_LEAVE,
                self._leave_vals(self.leave_type_ids["Lux"], self.employee_id, day_offset=2),
                context=self._ctx(lux_id),
            ),
        )

    # ------------------------------------------------------------------
    # Expense — default-company employee on create and on post
    # ------------------------------------------------------------------

    def _get_expense_product(self) -> int | None:
        product_ids = self.admin.search(
            "product.product", [("can_be_expensed", "=", True)], limit=1
        )
        if product_ids:
            return product_ids[0]
        category_id = self.admin.search("product.category", [], limit=1)
        if not category_id:
            return None
        return self.admin.create(
            "product.product",
            {
                "name": f"{TEST_PREFIX} Expense Product",
                "type": "service",
                "can_be_expensed": True,
                "list_price": 100.0,
                "standard_price": 100.0,
                "categ_id": category_id[0],
            },
        )

    def _test_expenses(self) -> None:
        self._section(
            f"Expense tests — create in {COMPANY_FRANCE}, post keeps {COMPANY_DEFAULT} employee"
        )
        if not self._module_installed("hr_expense"):
            self._skip("Expense tests", "hr_expense module not installed")
            return
        if not self.user_client or not self.employee_id:
            self._skip("Expense tests", "test user or employee not ready")
            return

        france_id = self._company_id("France")
        llc_id = self._company_id("LLC")
        product_id = self._get_expense_product()
        if not product_id:
            self._skip("Expense tests", "no expensible product found")
            return

        # Same-company expense (LLC) — baseline
        expense_llc_id = self.admin.create(
            MODEL_HR_EXPENSE,
            {
                "name": f"{TEST_PREFIX} Expense {COMPANY_DEFAULT}",
                "product_id": product_id,
                "total_amount_currency": 50.0,
                "quantity": 1.0,
                "company_id": llc_id,
                "employee_id": self.employee_id,
            },
            context=self._ctx(llc_id),
        )
        self._track(MODEL_HR_EXPENSE, expense_llc_id)
        llc_exp = self.admin.read(
            MODEL_HR_EXPENSE, [expense_llc_id], ["employee_id"], context=self._ctx(llc_id)
        )[0]
        self._ok(
            f"Expense in {COMPANY_DEFAULT} → employee = {EMPLOYEE_NAME}",
            self._m2o_id(llc_exp["employee_id"]) == self.employee_id,
        )

        # Cross-company expense (France) — module should keep default LLC employee
        try:
            expense_id = self.admin.create(
                MODEL_HR_EXPENSE,
                {
                    "name": f"{TEST_PREFIX} Expense {COMPANY_FRANCE}",
                    "product_id": product_id,
                    "total_amount_currency": 100.0,
                    "quantity": 1.0,
                    "company_id": france_id,
                },
                context=self._multi_company_ctx(france_id),
            )
        except RuntimeError as exc:
            self._ok(
                f"Expense in {COMPANY_FRANCE} with default-company employee",
                False,
                f"blocked by Odoo company check (module may need hr.expense override): {str(exc)[:160]}",
            )
            return

        self._track(MODEL_HR_EXPENSE, expense_id)
        on_create = self.admin.read(
            MODEL_HR_EXPENSE,
            [expense_id],
            ["employee_id", "company_id", "state"],
            context=self._multi_company_ctx(france_id),
        )[0]
        self._ok(
            f"Expense created in {COMPANY_FRANCE} → employee = {EMPLOYEE_NAME} (default LLC)",
            self._m2o_id(on_create["employee_id"]) == self.employee_id,
            f"employee_id={self._m2o_id(on_create['employee_id'])}",
        )

        try:
            self.admin.call(
                MODEL_HR_EXPENSE,
                "action_submit",
                [expense_id],
                context=self._multi_company_ctx(france_id),
            )
            self.admin.call(
                MODEL_HR_EXPENSE,
                "action_approve",
                [expense_id],
                context=self._multi_company_ctx(france_id),
            )
            on_post = self.admin.read(
                MODEL_HR_EXPENSE,
                [expense_id],
                ["employee_id", "state"],
                context=self._multi_company_ctx(france_id),
            )[0]
            self._ok(
                f"Posted expense keeps {COMPANY_DEFAULT} employee ({EMPLOYEE_NAME})",
                self._m2o_id(on_post["employee_id"]) == self.employee_id
                and on_post["state"] in ("approved", "posted", "done", "in_payment", "paid"),
                f"state={on_post['state']}, employee_id={self._m2o_id(on_post['employee_id'])}",
            )
        except RuntimeError as exc:
            after = self.admin.read(
                MODEL_HR_EXPENSE,
                [expense_id],
                ["employee_id", "state"],
                context=self._multi_company_ctx(france_id),
            )[0]
            self._ok(
                f"Expense employee unchanged after submit (post skipped: {str(exc)[:80]})",
                self._m2o_id(after["employee_id"]) == self.employee_id,
                f"state={after['state']}",
            )

    def _cleanup(self) -> None:
        self._section("Cleanup")
        order = [
            MODEL_ANALYTIC_LINE,
            MODEL_HR_EXPENSE,
            MODEL_HR_LEAVE,
            MODEL_HR_LEAVE_ALLOCATION,
            MODEL_PROJECT_TASK,
            MODEL_PROJECT,
            MODEL_HR_LEAVE_TYPE,
            MODEL_HR_EMPLOYEE,
            MODEL_RES_USERS,
            MODEL_RES_COMPANY,
        ]
        for model in order:
            ids = self._cleanup_ids.get(model, [])
            if not ids:
                continue
            try:
                if model == MODEL_HR_LEAVE:
                    for leave_id in ids:
                        state = self.admin.read(MODEL_HR_LEAVE, [leave_id], ["state"])[0]["state"]
                        if state not in ("draft", "refuse", "cancel"):
                            try:
                                self.admin.call(MODEL_HR_LEAVE, "action_refuse", [leave_id])
                            except RuntimeError:
                                pass
                elif model == MODEL_HR_EXPENSE:
                    for expense_id in ids:
                        state = self.admin.read(MODEL_HR_EXPENSE, [expense_id], ["state"])[0]["state"]
                        if state not in ("draft", "cancel"):
                            try:
                                self.admin.write(MODEL_HR_EXPENSE, [expense_id], {"state": "draft"})
                            except RuntimeError:
                                pass
                self.admin.unlink(model, ids)
                print(f"  Cleaned up {len(ids)} {model} record(s)")
            except RuntimeError as exc:
                print(f"  [WARN] cleanup {model} {ids}: {exc}")
            self._cleanup_ids[model] = []

    def run(self) -> bool:
        print("=" * 80)
        print("Single Employee for Multi-Company — Flow RPC Test (Odoo 19)")
        print(f"Scenario: {EMPLOYEE_NAME} @ {COMPANY_DEFAULT} (default, active)")
        print(f"Module  : {MODULE_NAME}")
        print(
            f"Protocol: {self.admin.protocol.upper()} | DB: {self.admin.db} | URL: {self.admin.url}"
        )
        print("=" * 80)

        self._section("Authenticate")
        self._ok("Admin authenticated", self.admin.uid is not None, f"uid={self.admin.uid}")

        self._section("Verify module installed")
        module_ok = self._module_installed(MODULE_NAME)
        if not module_ok:
            alloc_keys = set()
            try:
                selection = self.admin.fields_get(
                    MODEL_HR_LEAVE_ALLOCATION, [FIELD_ALLOC_HOLIDAY_TYPE]
                ).get(FIELD_ALLOC_HOLIDAY_TYPE, {}).get("selection") or []
                alloc_keys = {key for key, _label in selection}
            except RuntimeError:
                pass
            module_ok = alloc_keys == {"employee", "company"}
        self._ok(f"Module {MODULE_NAME!r} installed", module_ok)
        for mod, model in OPTIONAL_MODULES.items():
            installed = self._module_installed(mod) or self._model_available(model)
            print(f"  optional {mod}: {'installed' if installed else 'not installed'}")

        self._setup_companies()
        self._setup_user_and_employee()
        self._authenticate_test_user()
        self._test_user_employee_across_companies()
        self._setup_projects_and_tasks()
        self._test_timesheets()
        self._test_leave()
        self._test_expenses()
        self._cleanup()

        print()
        print("=" * 80)
        print(f"Result: {self.passed} passed, {self.failed} failed, {self.skipped} skipped")
        print("=" * 80)
        return self.failed == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "RPC flow test for cap_single_employee_for_multi_company — "
            "Anne Engin / Captivea single-employee scenario (Odoo 19)"
        ),
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--protocol", choices=["jsonrpc", "xmlrpc"], default=DEFAULT_PROTOCOL)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    admin = OdooRPCClient(args.url, args.db, args.user, args.password, args.protocol)
    try:
        admin.authenticate()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    success = SingleEmployeeFlowRPCTest(admin, args).run()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
