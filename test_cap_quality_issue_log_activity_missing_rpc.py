#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reproduce mail.activity "Missing Record" via cap_quality_issue_log (Odoo 19).

Uses the real model code path from models/quality_issue_log.py:
  - ask_for_review()     → creates mail.activity for manager + action_close_dialog()
  - refuse_review()      → does NOT remove the activity (bug)
  - accept_review()      → does NOT remove the activity (bug)

Run (plain Python 3, no odoo-bin shell):

    python3 models/test_cap_quality_issue_log_activity_missing_rpc.py
    python3 models/test_cap_quality_issue_log_activity_missing_rpc.py \\
        --url http://localhost:8069 --db odoo --user admin --password admin
    python3 models/test_cap_quality_issue_log_activity_missing_rpc.py --protocol xmlrpc

Optional: reuse existing logins instead of creating test users:

    python3 models/test_cap_quality_issue_log_activity_missing_rpc.py \\
        --employee-login qa_employee --manager-login qa_manager
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
# Connection defaults
# ---------------------------------------------------------------------------
DEFAULT_URL = "http://localhost:8069"
DEFAULT_DB = "odoo"
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "admin"
DEFAULT_PROTOCOL = "jsonrpc"

MODULE_NAME = "cap_quality_issue_log"
TEST_PREFIX = "RPC Activity Missing"

# ---------------------------------------------------------------------------
# From models/quality_issue_log.py
# ---------------------------------------------------------------------------
MODEL_QUALITY_ISSUE_LOG = "quality.issue.log"
MODEL_QUALITY_ISSUE_TYPE = "quality.issue.type"
MODEL_QUALITY_CATEGORY = "quality.category"
MODEL_MAIL_ACTIVITY = "mail.activity"
MODEL_HR_EMPLOYEE = "hr.employee"
MODEL_RES_USERS = "res.users"
MODEL_RES_COMPANY = "res.company"

FIELD_LOG_EMPLOYEE = "employee_id"
FIELD_LOG_STATE = "state"
FIELD_LOG_TYPE = "log_type"
FIELD_LOG_ISSUE_TYPE = "quality_issue_type"
FIELD_LOG_DESCRIPTION = "description"
FIELD_LOG_SCORE_IMPACT = "score_impact"
FIELD_LOG_DATE = "logged_date"

METHOD_ASK_FOR_REVIEW = "ask_for_review"
METHOD_REFUSE_REVIEW = "refuse_review"
METHOD_ACCEPT_REVIEW = "accept_review"
METHOD_ACTIVITY_OPEN = "action_open_document"
METHOD_ACTIVITY_FEEDBACK = "action_feedback"

ACTIVITY_SUMMARY = "Review Quality Issue"
TODO_TYPE_NAMES = ["Todo", "To Do", "To-Do"]  # same search as ask_for_review()

CMD_SET = 6
MISSING_RECORD_MARKERS = (
    "missing record",
    "does not exist",
    "has been deleted",
    "record not found",
)


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
                f"Authentication failed for {self.username!r}. Check URL, DB, login, password."
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
            raise RuntimeError("Not authenticated.")
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

    def search(self, model: str, domain: list, limit: int | None = None) -> list[int]:
        kwargs: dict[str, Any] = {}
        if limit is not None:
            kwargs["limit"] = limit
        return self.execute_kw(model, "search", [domain], kwargs)

    def read(self, model: str, ids: list[int], fields: list[str]) -> list[dict]:
        return self.execute_kw(model, "read", [ids, fields])

    def create(self, model: str, vals: dict) -> int:
        return self.execute_kw(model, "create", [vals])

    def write(self, model: str, ids: list[int], vals: dict) -> bool:
        return self.execute_kw(model, "write", [ids, vals])

    def unlink(self, model: str, ids: list[int]) -> bool:
        return self.execute_kw(model, "unlink", [ids])

    def call(self, model: str, method: str, ids: list[int], *args) -> Any:
        return self.execute_kw(model, method, [ids] + list(args))


def is_missing_record_error(exc: RuntimeError) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in MISSING_RECORD_MARKERS)


class ActivityMissingRecordReproducer:
    """
    End-to-end reproducer for mail.activity Missing Record after ask_for_review().

    Simulates what happens when a manager's UI still references an activity that
    Odoo deleted (mark as done / action_feedback / manual unlink).
    """

    def __init__(self, admin: OdooRPCClient, args: argparse.Namespace):
        self.admin = admin
        self.args = args
        self.passed = 0
        self.failed = 0
        self._cleanup: dict[str, list[int]] = {
            MODEL_QUALITY_ISSUE_LOG: [],
            MODEL_QUALITY_ISSUE_TYPE: [],
            MODEL_QUALITY_CATEGORY: [],
            MODEL_HR_EMPLOYEE: [],
            MODEL_RES_USERS: [],
        }
        self.company_id: int | None = None
        self.employee_user_id: int | None = None
        self.manager_user_id: int | None = None
        self.employee_id: int | None = None
        self.manager_employee_id: int | None = None

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

    def _track(self, model: str, record_id: int) -> None:
        self._cleanup.setdefault(model, []).append(record_id)

    def _module_installed(self) -> bool:
        return bool(
            self.admin.search(
                "ir.module.module",
                [("name", "=", MODULE_NAME), ("state", "=", "installed")],
            )
        )

    def _get_or_create_user(self, login: str, name: str) -> int:
        existing = self.admin.search(MODEL_RES_USERS, [("login", "=", login)], limit=1)
        if existing:
            return existing[0]
        user_id = self.admin.create(
            MODEL_RES_USERS,
            {
                "name": name,
                "login": login,
                "email": f"{login}@example.com",
                "password": "test123",
            },
        )
        self._track(MODEL_RES_USERS, user_id)
        return user_id

    def _get_or_create_employee(
        self,
        name: str,
        company_id: int,
        user_id: int | None = None,
        parent_id: int | None = None,
    ) -> int:
        domain = [("name", "=", name), ("company_id", "=", company_id)]
        existing = self.admin.search(MODEL_HR_EMPLOYEE, domain, limit=1)
        vals: dict[str, Any] = {"name": name, "company_id": company_id}
        if user_id:
            vals["user_id"] = user_id
        if parent_id:
            vals["parent_id"] = parent_id
        if existing:
            # If the employee exists, simply return its ID without attempting to write.
            return existing[0]
        employee_id = self.admin.create(MODEL_HR_EMPLOYEE, vals)
        self._track(MODEL_HR_EMPLOYEE, employee_id)
        return employee_id

    def _setup_users(self) -> bool:
        self.company_id = self.admin.search(MODEL_RES_COMPANY, [], limit=1)[0]

        if self.args.employee_login and self.args.manager_login:
            emp_users = self.admin.search(
                MODEL_RES_USERS, [("login", "=", self.args.employee_login)], limit=1
            )
            mgr_users = self.admin.search(
                MODEL_RES_USERS, [("login", "=", self.args.manager_login)], limit=1
            )
            if not emp_users or not mgr_users:
                self._ok(
                    "Existing employee/manager logins found",
                    False,
                    f"employee={self.args.employee_login!r} manager={self.args.manager_login!r}",
                )
                return False
            self.employee_user_id = emp_users[0]
            self.manager_user_id = mgr_users[0]
            emp_emps = self.admin.search(
                MODEL_HR_EMPLOYEE, [("user_id", "=", self.employee_user_id)], limit=1
            )
            mgr_emps = self.admin.search(
                MODEL_HR_EMPLOYEE, [("user_id", "=", self.manager_user_id)], limit=1
            )
            if not emp_emps:
                self._ok("Employee record linked to employee login", False)
                return False
            if not mgr_emps:
                self._ok("Employee record linked to manager login", False)
                return False
            self.employee_id = emp_emps[0]
            self.manager_employee_id = mgr_emps[0]
            self.admin.write(
                MODEL_HR_EMPLOYEE,
                [self.employee_id],
                {"parent_id": self.manager_employee_id, "company_id": self.company_id},
            )
        else:
            # Use the admin user for both roles but create distinct employee records without linking to the same user.
            self.manager_user_id = self.admin.uid
            self.employee_user_id = self.admin.uid
            # Manager employee without a user link.
            # Manager employee linked to admin user.
            self.manager_employee_id = self._get_or_create_employee(
                f"{TEST_PREFIX} Manager Emp",
                self.company_id,
                user_id=self.manager_user_id,
            )
            # Employee without a user link, parent is manager.
            self.employee_id = self._get_or_create_employee(
                f"{TEST_PREFIX} Employee Emp",
                self.company_id,
                user_id=None,
                parent_id=self.manager_employee_id,
            )
            print("  Created manager and employee HR records without user links, using admin UID for actions.")

        emp = self.admin.read(
            MODEL_HR_EMPLOYEE,
            [self.employee_id],
            ["parent_id", "user_id"],
        )[0]
        parent_ok = bool(emp.get("parent_id"))
        self._ok("Employee has manager (parent_id)", parent_ok, str(emp.get("parent_id")))
        mgr = self.admin.read(
            MODEL_HR_EMPLOYEE,
            [self.manager_employee_id],
            ["user_id"],
        )[0]
        mgr_user_ok = bool(mgr.get("user_id"))
        self._ok("Manager employee has related user", mgr_user_ok, str(mgr.get("user_id")))
        return parent_ok and mgr_user_ok

    def _ensure_todo_activity_type(self) -> int | None:
        """ask_for_review searches by name; create To-Do if missing (e.g. translated DB)."""
        todo_ids = self.admin.search(
            "mail.activity.type",
            [("name", "in", TODO_TYPE_NAMES)],
            limit=1,
        )
        if todo_ids:
            return todo_ids[0]
        return self.admin.create(
            "mail.activity.type",
            {"name": "To-Do", "summary": "To-Do", "icon": "fa-tasks"},
        )

    def _create_quality_log(self) -> int:
        category_id = self.admin.create(
            MODEL_QUALITY_CATEGORY,
            {"name": f"{TEST_PREFIX} Category", "weight": 10.0},
        )
        self._track(MODEL_QUALITY_CATEGORY, category_id)
        issue_type_id = self.admin.create(
            MODEL_QUALITY_ISSUE_TYPE,
            {
                "name": f"{TEST_PREFIX} Issue Type",
                "quality_category": category_id,
                "score_impact": 5.0,
                "state": "draft",
            },
        )
        self._track(MODEL_QUALITY_ISSUE_TYPE, issue_type_id)
        log_id = self.admin.create(
            MODEL_QUALITY_ISSUE_LOG,
            {
                FIELD_LOG_DATE: str(date.today()),
                FIELD_LOG_EMPLOYEE: self.employee_id,
                FIELD_LOG_DESCRIPTION: f"{TEST_PREFIX} penalty log for activity test",
                FIELD_LOG_SCORE_IMPACT: 5.0,
                FIELD_LOG_ISSUE_TYPE: issue_type_id,
                FIELD_LOG_TYPE: "penalty",
                FIELD_LOG_STATE: "enabled",
            },
        )
        self._track(MODEL_QUALITY_ISSUE_LOG, log_id)
        return log_id

    def _find_review_activity(self, log_id: int, manager_uid: int) -> list[int]:
        return self.admin.search(
            MODEL_MAIL_ACTIVITY,
            [
                ("summary", "=", ACTIVITY_SUMMARY),
                ("res_model", "=", MODEL_QUALITY_ISSUE_LOG),
                ("res_id", "=", log_id),
                ("user_id", "=", manager_uid),
            ],
        )

    def _client_as(self, login: str, password: str) -> OdooRPCClient:
        client = OdooRPCClient(
            self.args.url,
            self.args.db,
            login,
            password,
            self.args.protocol,
        )
        client.authenticate()
        return client

    def _expect_missing_on_read(self, client: OdooRPCClient, activity_id: int, label: str) -> bool:
        try:
            client.read(MODEL_MAIL_ACTIVITY, [activity_id], ["summary", "user_id"])
        except RuntimeError as exc:
            return self._ok(label, is_missing_record_error(exc), str(exc)[:220])
        return self._ok(label, False, "expected Missing Record error but read succeeded")

    def _expect_missing_on_open(self, client: OdooRPCClient, activity_id: int, label: str) -> bool:
        try:
            client.call(MODEL_MAIL_ACTIVITY, METHOD_ACTIVITY_OPEN, [activity_id])
        except RuntimeError as exc:
            return self._ok(label, is_missing_record_error(exc), str(exc)[:220])
        return self._ok(
            label,
            False,
            "expected Missing Record on action_open_document but call succeeded",
        )

    def _scenario_ask_for_review_creates_activity(self, log_id: int) -> int | None:
        """Step 1: call quality.issue.log.ask_for_review() exactly like the UI button."""
        print("\n--- Scenario 1: ask_for_review() creates mail.activity ---")

        self._ensure_todo_activity_type()

        employee_client = self._client_as(
            self.args.employee_login or self._login_for_uid(self.employee_user_id),
            self.args.employee_password or self.args.password,
        )
        employee_client.call(MODEL_QUALITY_ISSUE_LOG, METHOD_ASK_FOR_REVIEW, [log_id])

        log_data = self.admin.read(MODEL_QUALITY_ISSUE_LOG, [log_id], [FIELD_LOG_STATE])[0]
        self._ok(
            f"{MODEL_QUALITY_ISSUE_LOG}.{METHOD_ASK_FOR_REVIEW} sets state=reviewing",
            log_data[FIELD_LOG_STATE] == "reviewing",
            log_data[FIELD_LOG_STATE],
        )

        activity_ids = self._find_review_activity(log_id, self.manager_user_id)
        if not activity_ids:
            self._ok(
                f"{METHOD_ASK_FOR_REVIEW} created {MODEL_MAIL_ACTIVITY} for manager",
                False,
                "NO activity found — check parent user & To-Do activity type name",
            )
            return None

        activity_id = activity_ids[0]
        activity = self.admin.read(
            MODEL_MAIL_ACTIVITY,
            [activity_id],
            ["summary", "user_id", "res_model", "res_id"],
        )[0]
        self._ok(
            f"{METHOD_ASK_FOR_REVIEW} created {MODEL_MAIL_ACTIVITY} for manager",
            activity["summary"] == ACTIVITY_SUMMARY
            and activity["res_model"] == MODEL_QUALITY_ISSUE_LOG
            and activity["res_id"] == log_id,
            f"id={activity_id} user_id={activity['user_id']}",
        )
        return activity_id

    def _scenario_stale_read_after_unlink(self, activity_id: int) -> None:
        """Step 2: activity deleted while manager session still references it."""
        print("\n--- Scenario 2: Missing Record after activity unlink (stale UI) ---")

        manager_login = self.args.manager_login or self._login_for_uid(self.manager_user_id)
        manager_client = self._client_as(manager_login, self.args.manager_password or self.args.password)

        manager_client.read(MODEL_MAIL_ACTIVITY, [activity_id], ["summary"])
        self._ok("Manager can read activity before delete", True, f"id={activity_id}")

        self.admin.unlink(MODEL_MAIL_ACTIVITY, [activity_id])
        self._ok("Activity unlinked (simulates Mark Done)", True, f"id={activity_id}")

        self._expect_missing_on_read(
            manager_client,
            activity_id,
            f"Manager read deleted {MODEL_MAIL_ACTIVITY} → Missing Record",
        )
        self._expect_missing_on_open(
            manager_client,
            activity_id,
            f"Manager {METHOD_ACTIVITY_OPEN} on deleted activity → Missing Record",
        )

    def _scenario_refuse_review_leaves_activity(self, log_id: int) -> None:
        """
        Step 3: refuse_review() does not unlink activity (models/quality_issue_log.py bug).
        Marking done then reading again triggers Missing Record.
        """
        print("\n--- Scenario 3: refuse_review() leaves activity → then deleted ---")

        self.admin.write(MODEL_QUALITY_ISSUE_LOG, [log_id], {FIELD_LOG_STATE: "enabled"})
        employee_client = self._client_as(
            self.args.employee_login or self._login_for_uid(self.employee_user_id),
            self.args.employee_password or self.args.password,
        )
        employee_client.call(MODEL_QUALITY_ISSUE_LOG, METHOD_ASK_FOR_REVIEW, [log_id])

        activity_ids = self._find_review_activity(log_id, self.manager_user_id)
        if not activity_ids:
            self._ok("Activity exists before refuse_review", False)
            return
        activity_id = activity_ids[-1]

        manager_login = self.args.manager_login or self._login_for_uid(self.manager_user_id)
        manager_client = self._client_as(manager_login, self.args.manager_password or self.args.password)
        manager_client.call(MODEL_QUALITY_ISSUE_LOG, METHOD_REFUSE_REVIEW, [log_id])

        still_there = self._find_review_activity(log_id, self.manager_user_id)
        self._ok(
            f"{METHOD_REFUSE_REVIEW} does NOT remove {MODEL_MAIL_ACTIVITY} (known gap)",
            activity_id in still_there,
            f"activity ids still present: {still_there}",
        )

        manager_client.call(MODEL_MAIL_ACTIVITY, METHOD_ACTIVITY_FEEDBACK, [activity_id])
        self._expect_missing_on_read(
            manager_client,
            activity_id,
            f"After {METHOD_ACTIVITY_FEEDBACK}, stale read → Missing Record",
        )

    def _scenario_accept_review_leaves_activity(self) -> None:
        """Step 4: same gap when manager accepts review."""
        print("\n--- Scenario 4: accept_review() leaves activity → then deleted ---")

        log_id = self._create_quality_log()
        employee_client = self._client_as(
            self.args.employee_login or self._login_for_uid(self.employee_user_id),
            self.args.employee_password or self.args.password,
        )
        employee_client.call(MODEL_QUALITY_ISSUE_LOG, METHOD_ASK_FOR_REVIEW, [log_id])

        activity_ids = self._find_review_activity(log_id, self.manager_user_id)
        if not activity_ids:
            self._ok("Activity exists before accept_review", False)
            return
        activity_id = activity_ids[-1]

        manager_login = self.args.manager_login or self._login_for_uid(self.manager_user_id)
        manager_client = self._client_as(manager_login, self.args.manager_password or self.args.password)
        manager_client.call(MODEL_QUALITY_ISSUE_LOG, METHOD_ACCEPT_REVIEW, [log_id])

        still_there = self._find_review_activity(log_id, self.manager_user_id)
        self._ok(
            f"{METHOD_ACCEPT_REVIEW} does NOT remove {MODEL_MAIL_ACTIVITY} (known gap)",
            activity_id in still_there,
            f"activity ids still present: {still_there}",
        )

        manager_client.call(MODEL_MAIL_ACTIVITY, METHOD_ACTIVITY_FEEDBACK, [activity_id])
        self._expect_missing_on_read(
            manager_client,
            activity_id,
            f"After accept + feedback, stale read → Missing Record",
        )

    def _login_for_uid(self, uid: int) -> str:
        return self.admin.read(MODEL_RES_USERS, [uid], ["login"])[0]["login"]

    def _cleanup_records(self) -> None:
        print("\n--- Cleanup ---")
        order = [
            MODEL_QUALITY_ISSUE_LOG,
            MODEL_QUALITY_ISSUE_TYPE,
            MODEL_QUALITY_CATEGORY,
            MODEL_HR_EMPLOYEE,
            MODEL_RES_USERS,
        ]
        for model in order:
            ids = self._cleanup.get(model, [])
            if not ids:
                continue
            try:
                self.admin.unlink(model, ids)
                print(f"  Removed {len(ids)} {model} record(s)")
            except RuntimeError as exc:
                print(f"  [WARN] cleanup {model}: {exc}")
            self._cleanup[model] = []

    def run(self) -> bool:
        print("=" * 80)
        print("CAP Quality Issue Log — mail.activity Missing Record Reproducer (Odoo 19)")
        print(f"Module: {MODULE_NAME}")
        print(
            f"Protocol: {self.args.protocol.upper()} | DB: {self.args.db} | URL: {self.args.url}"
        )
        print("=" * 80)

        self._ok(f"Module {MODULE_NAME!r} installed", self._module_installed())
        if not self._setup_users():
            print("\nAborting: fix employee/manager setup first.")
            return False

        print(f"  company_id={self.company_id}")
        print(f"  employee_user_id={self.employee_user_id} employee_id={self.employee_id}")
        print(f"  manager_user_id={self.manager_user_id} manager_employee_id={self.manager_employee_id}")

        log_id = self._create_quality_log()
        activity_id = self._scenario_ask_for_review_creates_activity(log_id)
        if activity_id:
            self._scenario_stale_read_after_unlink(activity_id)
            self._scenario_refuse_review_leaves_activity(log_id)
        else:
            print("\nSkipping scenarios 2–4: ask_for_review did not create an activity.")

        self._scenario_accept_review_leaves_activity()

        print("=" * 80)
        print(f"Result: {self.passed} passed, {self.failed} failed")
        print("=" * 80)
        if self.failed == 0 and activity_id:
            print(
                "\nReproduced: mail.activity Missing Record after ask_for_review() flow.\n"
                "Root code: models/quality_issue_log.py → ask_for_review() / refuse_review() / accept_review()"
            )

        if not self.args.keep_data:
            self._cleanup_records()
        return self.failed == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Reproduce mail.activity Missing Record using cap_quality_issue_log.ask_for_review()"
        ),
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--user", default=DEFAULT_USER, help="Admin login for setup")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Admin password")
    parser.add_argument(
        "--employee-login",
        help="Use existing employee user instead of creating a test user",
    )
    parser.add_argument("--employee-password", help="Password for --employee-login")
    parser.add_argument(
        "--manager-login",
        help="Use existing manager/approver user (the User: N in the error)",
    )
    parser.add_argument("--manager-password", help="Password for --manager-login")
    parser.add_argument(
        "--protocol",
        choices=["jsonrpc", "xmlrpc"],
        default=DEFAULT_PROTOCOL,
    )
    parser.add_argument(
        "--keep-data",
        action="store_true",
        help="Do not delete test records after run",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    admin = OdooRPCClient(args.url, args.db, args.user, args.password, args.protocol)
    try:
        uid = admin.authenticate()
        print(f"Authenticated admin uid={uid}")
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    success = ActivityMissingRecordReproducer(admin, args).run()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
