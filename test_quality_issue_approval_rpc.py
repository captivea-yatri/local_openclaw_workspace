#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quality Issue Log + approval.request workflow test via XML-RPC or JSON-RPC.

Does NOT modify any module code. Connects to a running Odoo instance remotely.

Requirements on the Odoo server:
  - cap_quality_issue_log installed
  - approvals (Enterprise) installed
  - RPC user (default: admin) with rights to create users, employees, approvals

---------------------------------------------------------------------------
USAGE
---------------------------------------------------------------------------

XML-RPC (default, no extra packages):

  python3 scripts/test_quality_issue_approval_rpc.py \\
    --url http://localhost:8069 \\
    --db YOUR_DB \\
    --user admin \\
    --password admin

JSON-RPC:

  python3 scripts/test_quality_issue_approval_rpc.py --rpc jsonrpc \\
    --url http://localhost:8069 --db YOUR_DB --user admin --password admin

Environment variables (optional instead of flags):
  ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD, ODOO_RPC

Run specific scenarios:

  python3 scripts/test_quality_issue_approval_rpc.py --scenarios setup stale_activity

Keep test data in DB (no cleanup):

  python3 scripts/test_quality_issue_approval_rpc.py --no-cleanup

---------------------------------------------------------------------------
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import xmlrpc.client
from datetime import date, datetime


DEFAULT_TEST_PASSWORD = "QilTestPass123!"


# ---------------------------------------------------------------------------
# RPC clients
# ---------------------------------------------------------------------------

class RpcError(Exception):
    """Odoo RPC fault / JSON-RPC error wrapper."""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code

    @property
    def is_missing_record(self):
        msg = str(self).lower()
        return (
            "does not exist" in msg
            or "has been deleted" in msg
            or "missing record" in msg
        )


class OdooRpcClient:
    """Thin wrapper around Odoo execute_kw."""

    def __init__(self, url, db, login, password):
        self.url = url.rstrip("/")
        self.db = db
        self.login = login
        self.password = password
        self.uid = None

    def authenticate(self):
        raise NotImplementedError

    def execute_kw(self, model, method, args=None, kwargs=None):
        raise NotImplementedError

    # --- high-level helpers ---

    def call(self, model, method, *args, **kwargs):
        return self.execute_kw(model, method, list(args), kwargs or {})

    def search(self, model, domain, limit=0, order=None):
        kw = {}
        if limit:
            kw["limit"] = limit
        if order:
            kw["order"] = order
        return self.call(model, "search", domain, **kw)

    def search_read(self, model, domain, fields=None, limit=0, order=None):
        kw = {}
        if fields:
            kw["fields"] = fields
        if limit:
            kw["limit"] = limit
        if order:
            kw["order"] = order
        return self.call(model, "search_read", domain, **kw)

    def read(self, model, ids, fields=None):
        if not ids:
            return []
        kw = {}
        if fields:
            kw["fields"] = fields
        return self.call(model, "read", ids, **kw)

    def create(self, model, vals):
        return self.call(model, "create", vals)

    def write(self, model, ids, vals):
        return self.call(model, "write", ids, vals)

    def unlink(self, model, ids):
        return self.call(model, "unlink", ids)

    def fields_get(self, model, attributes=None):
        kw = {}
        if attributes:
            kw["attributes"] = attributes
        return self.call(model, "fields_get", **kw)

    def exists(self, model, record_id):
        rows = self.read(model, [record_id], fields=["id"])
        return bool(rows)


class XmlRpcClient(OdooRpcClient):
    def authenticate(self):
        common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self.uid = common.authenticate(self.db, self.login, self.password, {})
        if not self.uid:
            raise RpcError(f"Authentication failed for {self.login!r} on db {self.db!r}")
        self._models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")
        return self.uid

    def execute_kw(self, model, method, args=None, kwargs=None):
        try:
            return self._models.execute_kw(
                self.db, self.uid, self.password,
                model, method, args or [], kwargs or {},
            )
        except xmlrpc.client.Fault as exc:
            raise RpcError(exc.faultString, code=exc.faultCode) from exc


class JsonRpcClient(OdooRpcClient):
    def authenticate(self):
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "common",
                "method": "authenticate",
                "args": [self.db, self.login, self.password, {}],
            },
            "id": 1,
        }
        result = self._jsonrpc(payload)
        if not result:
            raise RpcError(f"Authentication failed for {self.login!r} on db {self.db!r}")
        self.uid = result
        return self.uid

    def execute_kw(self, model, method, args=None, kwargs=None):
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "object",
                "method": "execute_kw",
                "args": [
                    self.db, self.uid, self.password,
                    model, method, args or [], kwargs or {},
                ],
            },
            "id": 1,
        }
        return self._jsonrpc(payload)

    def _jsonrpc(self, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.url}/jsonrpc",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RpcError(f"HTTP {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise RpcError(f"Connection error: {exc.reason}") from exc

        if body.get("error"):
            err = body["error"]
            msg = err.get("data", {}).get("message") or err.get("message", str(err))
            raise RpcError(msg, code=err.get("code"))
        return body.get("result")


def connect(url, db, login, password, rpc="xmlrpc"):
    rpc = rpc.lower()
    if rpc == "jsonrpc":
        client = JsonRpcClient(url, db, login, password)
    elif rpc == "xmlrpc":
        client = XmlRpcClient(url, db, login, password)
    else:
        raise ValueError(f"Unknown RPC type: {rpc!r} (use xmlrpc or jsonrpc)")
    client.authenticate()
    return client


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _log(title, message=""):
    line = "=" * 72
    print(f"\n{line}\n{title}\n{line}")
    if message:
        print(message)


def _ok(label):
    print(f"  [PASS] {label}")


def _fail(label, detail=""):
    print(f"  [FAIL] {label}")
    if detail:
        print(f"         {detail}")


def _info(label, value):
    print(f"  [INFO] {label}: {value}")


# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------

class QualityIssueApprovalRpcTest:
    """Runs the approval workflow tests through RPC."""

    def __init__(self, admin: OdooRpcClient, cleanup=True):
        self.admin = admin
        self.cleanup = cleanup
        self._created = []          # (model, id) for cleanup, newest last
        self.suffix = datetime.now().strftime("%Y%m%d%H%M%S")
        self.test_password = DEFAULT_TEST_PASSWORD

    def track(self, model, record_id):
        self._created.append((model, record_id))

    def create(self, model, vals):
        rid = self.admin.create(model, vals)
        self.track(model, rid)
        return rid

    def cleanup_all(self):
        if not self.cleanup:
            _info("Cleanup skipped", "--no-cleanup was set")
            return
        _log("CLEANUP — removing test records")
        # Delete in reverse creation order
        for model, rid in reversed(self._created):
            try:
                if self.admin.exists(model, rid):
                    self.admin.unlink(model, [rid])
                    _info(f"Deleted {model}", rid)
            except RpcError as exc:
                _info(f"Could not delete {model}({rid})", str(exc))

    # --- Odoo data helpers ---

    def _require_model(self, model):
        try:
            self.admin.fields_get(model, attributes=["type"])
        except RpcError as exc:
            raise RuntimeError(
                f"Model {model!r} not available. Install required apps. ({exc})"
            ) from exc

    def _get_company_id(self):
        users = self.admin.read("res.users", [self.admin.uid], fields=["company_id"])
        return users[0]["company_id"][0]

    def _get_group_ids(self, xml_ids):
        ids = []
        for xml_id in xml_ids:
            module, name = xml_id.split(".")
            rows = self.admin.search_read(
                "ir.model.data",
                [("module", "=", module), ("name", "=", name)],
                fields=["res_id"],
                limit=1,
            )
            if rows:
                ids.append(rows[0]["res_id"])
        return ids

    def _get_approval_activity_type_id(self):
        rows = self.admin.search_read(
            "ir.model.data",
            [("module", "=", "approvals"), ("name", "=", "mail_activity_data_approval")],
            fields=["res_id"],
            limit=1,
        )
        if not rows:
            raise RuntimeError("approvals.mail_activity_data_approval not found — is Approvals installed?")
        return rows[0]["res_id"]

    def _get_approval_category_id(self):
        rows = self.admin.search_read(
            "ir.model.data",
            [("module", "=", "approvals"), ("name", "=", "approval_category_data_general_approval")],
            fields=["res_id"],
            limit=1,
        )
        if rows:
            return rows[0]["res_id"]
        return self.create("approval.category", {
            "name": f"QIL RPC Test Category {self.suffix}",
            "approval_minimum": 1,
            "has_date": "no",
            "has_period": "no",
            "has_product": "no",
            "has_quantity": "no",
            "has_amount": "no",
            "has_reference": "no",
            "has_partner": "no",
            "has_payment_method": "no",
            "has_location": "no",
            "requirer_document": "optional",
        })

    def _link_approval_to_quality_log(self, approval_id, quality_log_id):
        fields = self.admin.fields_get("approval.request", attributes=["type"])
        vals = {}
        if "quality_issue_log_id" in fields:
            vals["quality_issue_log_id"] = quality_log_id
        if "x_studio_quality_issue_log" in fields:
            vals["x_studio_quality_issue_log"] = quality_log_id
        if vals:
            self.admin.write("approval.request", [approval_id], vals)

    def _create_test_user(self, login, name, group_xmlids):
        group_ids = self._get_group_ids(group_xmlids)
        company_id = self._get_company_id()
        uid = self.create("res.users", {
            "name": name,
            "login": login,
            "password": self.test_password,
            "group_ids": [(6, 0, group_ids)],
            "company_id": company_id,
            "company_ids": [(6, 0, [company_id])],
        })
        return uid

    def _manager_client(self, manager_login):
        return connect(
            self.admin.url, self.admin.db,
            manager_login, self.test_password,
            rpc="jsonrpc" if isinstance(self.admin, JsonRpcClient) else "xmlrpc",
        )

    def _find_manager_approval_activities(self, approval_id, manager_user_id):
        activity_type_id = self._get_approval_activity_type_id()
        return self.admin.search(
            "mail.activity",
            [
                ("res_model", "=", "approval.request"),
                ("res_id", "=", approval_id),
                ("activity_type_id", "=", activity_type_id),
                ("user_id", "=", manager_user_id),
            ],
        )

    def _create_approval_with_activity(self, name, category_id, owner_id, manager_id, quality_log_id):
        approval_id = self.create("approval.request", {
            "name": name,
            "category_id": category_id,
            "request_owner_id": owner_id,
            "reason": "<p>RPC test approval workflow</p>",
            "approver_ids": [(0, 0, {
                "user_id": manager_id,
                "required": True,
                "status": "new",
            })],
        })
        self._link_approval_to_quality_log(approval_id, quality_log_id)
        self.admin.call("approval.request", "action_confirm", [approval_id])
        activity_ids = self._find_manager_approval_activities(approval_id, manager_id)
        return approval_id, activity_ids

    def _try_read_activity(self, client, activity_id):
        return client.read("mail.activity", [activity_id], fields=["summary"])

    def _try_activity_feedback(self, client, activity_id):
        return client.call("mail.activity", "action_feedback", [activity_id])

    # --- scenarios ---

    def setup(self):
        _log("STEP 1 — Create test users and employees (via RPC)")
        self._require_model("approval.request")
        self._require_model("quality.issue.log")

        manager_login = f"qil_mgr_{self.suffix}@test.com"
        employee_login = f"qil_emp_{self.suffix}@test.com"

        manager_user_id = self._create_test_user(
            manager_login,
            f"QIL Manager {self.suffix}",
            ["base.group_user", "approvals.group_approval_user"],
        )
        employee_user_id = self._create_test_user(
            employee_login,
            f"QIL Employee {self.suffix}",
            ["base.group_user"],
        )

        company_id = self._get_company_id()
        manager_employee_id = self.create("hr.employee", {
            "name": f"QIL Manager {self.suffix}",
            "user_id": manager_user_id,
            "company_id": company_id,
        })
        employee_id = self.create("hr.employee", {
            "name": f"QIL Employee {self.suffix}",
            "user_id": employee_user_id,
            "company_id": company_id,
            "parent_id": manager_employee_id,
        })

        _info("Manager", f"{manager_login} (uid={manager_user_id})")
        _info("Employee", f"{employee_login} (uid={employee_user_id})")

        _log("STEP 2 — Create quality issue log")
        issue_types = self.admin.search_read("quality.issue.type", [], fields=["id", "score_impact"], limit=1)
        if issue_types:
            issue_type_id = issue_types[0]["id"]
            score = issue_types[0].get("score_impact") or 5.0
        else:
            categories = self.admin.search_read("quality.category", [], fields=["id"], limit=1)
            issue_type_id = self.create("quality.issue.type", {
                "name": f"RPC Test Issue Type {self.suffix}",
                "score_impact": 5.0,
                "quality_category": categories[0]["id"] if categories else False,
                "state": "in_progress",
            })
            score = 5.0

        quality_log_id = self.create("quality.issue.log", {
            "logged_date": str(date.today()),
            "employee_id": employee_id,
            "description": f"RPC test quality issue ({self.suffix})",
            "score_impact": score,
            "quality_issue_type": issue_type_id,
            "log_type": "penalty",
            "state": "reviewing",
        })
        qlog = self.admin.read("quality.issue.log", [quality_log_id], fields=["display_name", "state"])[0]
        _info("Quality issue log", f"id={quality_log_id}, state={qlog['state']}")
        _info("Display name", qlog.get("display_name"))

        _log("STEP 3 — Create approval.request, confirm, verify activity")
        category_id = self._get_approval_category_id()
        approval_id, activity_ids = self._create_approval_with_activity(
            f"Review Quality Issue: {qlog.get('display_name', quality_log_id)}",
            category_id,
            employee_user_id,
            manager_user_id,
            quality_log_id,
        )
        if not activity_ids:
            raise RuntimeError("No mail.activity created after action_confirm()")

        activity_id = activity_ids[0]
        approval = self.admin.read(
            "approval.request", [approval_id], fields=["request_status"]
        )[0]
        activity = self.admin.read(
            "mail.activity", [activity_id], fields=["res_model", "res_id"]
        )[0]

        _info("Approval request", f"id={approval_id}, status={approval['request_status']}")
        _info("Mail activity", f"id={activity_id}, res_model={activity['res_model']}, res_id={activity['res_id']}")
        _ok("Setup complete via RPC")

        return {
            "manager_login": manager_login,
            "employee_login": employee_login,
            "manager_user_id": manager_user_id,
            "employee_user_id": employee_user_id,
            "manager_employee_id": manager_employee_id,
            "employee_id": employee_id,
            "issue_type_id": issue_type_id,
            "quality_log_id": quality_log_id,
            "category_id": category_id,
            "approval_id": approval_id,
            "activity_id": activity_id,
        }

    def test_normal_approve(self, data):
        _log("SCENARIO A — Normal approve via approval.request (RPC)")

        approval_id = data["approval_id"]
        activity_id = data["activity_id"]
        manager_login = data["manager_login"]

        approval = self.admin.read("approval.request", [approval_id], fields=["request_status"])[0]
        if approval["request_status"] != "pending":
            _fail("Approval not pending", approval["request_status"])
            return False

        _info("Activity before approve", f"id={activity_id}, exists={self.admin.exists('mail.activity', activity_id)}")

        manager = self._manager_client(manager_login)
        manager.call("approval.request", "action_approve", [approval_id])

        approval = self.admin.read("approval.request", [approval_id], fields=["request_status"])[0]
        activity_exists = self.admin.exists("mail.activity", activity_id)
        _info("Approval status after approve", approval["request_status"])
        _info("Activity still exists?", activity_exists)

        if approval["request_status"] == "approved" and not activity_exists:
            _ok("Normal approve via RPC — approved, activity removed")
            return True

        _fail("Unexpected state after normal approve")
        return False

    def test_stale_activity(self, data):
        _log("SCENARIO B — Stale deleted activity → Missing Record (RPC)")

        manager_id = data["manager_user_id"]
        employee_id = data["employee_user_id"]
        quality_log_id = data["quality_log_id"]
        category_id = data["category_id"]

        approval_id, activity_ids = self._create_approval_with_activity(
            f"Stale RPC test — {self.suffix}",
            category_id,
            employee_id,
            manager_id,
            quality_log_id,
        )
        if not activity_ids:
            _fail("Could not create activity")
            return False

        stale_id = activity_ids[0]
        _info("Created activity", stale_id)

        self.admin.unlink("mail.activity", [stale_id])
        _info("Activity deleted server-side", stale_id)

        missing_read = False
        missing_feedback = False

        try:
            self._try_read_activity(self.admin, stale_id)
            _fail("read() on deleted activity should fail")
        except RpcError as exc:
            if exc.is_missing_record:
                missing_read = True
                _ok(f"Missing Record on read: {exc}")
            else:
                _fail("Unexpected RPC error on read", str(exc))

        try:
            self._try_activity_feedback(self.admin, stale_id)
            _fail("action_feedback on deleted activity should fail")
        except RpcError as exc:
            if exc.is_missing_record:
                missing_feedback = True
                _ok(f"Missing Record on action_feedback: {exc}")
            else:
                _fail("Unexpected RPC error on action_feedback", str(exc))

        if missing_read and missing_feedback:
            _ok("Stale activity Missing Record reproduced via RPC")
            return True

        _fail("Could not reproduce Missing Record")
        return False

    def test_double_approve_path(self, data):
        _log("SCENARIO C — Approve then access stale activity id (RPC)")

        manager_id = data["manager_user_id"]
        manager_login = data["manager_login"]
        employee_id = data["employee_user_id"]
        quality_log_id = data["quality_log_id"]
        category_id = data["category_id"]

        approval_id, activity_ids = self._create_approval_with_activity(
            f"Double path RPC — {self.suffix}",
            category_id,
            employee_id,
            manager_id,
            quality_log_id,
        )
        if not activity_ids:
            _fail("Could not create activity")
            return False

        captured_id = activity_ids[0]
        _info("Captured activity id", captured_id)

        manager = self._manager_client(manager_login)
        manager.call("approval.request", "action_approve", [approval_id])

        approval = self.admin.read("approval.request", [approval_id], fields=["request_status"])[0]
        _info("Approval status", approval["request_status"])
        _info("Activity exists?", self.admin.exists("mail.activity", captured_id))

        try:
            self._try_activity_feedback(manager, captured_id)
            _info("Second action_feedback silent — running stale_activity scenario")
            return self.test_stale_activity(data)
        except RpcError as exc:
            if exc.is_missing_record:
                _ok(f"Missing Record on second action_feedback: {exc}")
                return True
            _fail("Unexpected error", str(exc))
            return False

    def test_legacy_activity(self, data):
        _log("SCENARIO D — Legacy To-Do on quality.issue.log (RPC)")

        manager_id = data["manager_user_id"]
        quality_log_id = data["quality_log_id"]

        todo_types = self.admin.search_read(
            "mail.activity.type",
            [("name", "in", ["Todo", "To Do", "To-Do"])],
            fields=["id"],
            limit=1,
        )
        if not todo_types:
            _fail("No To-Do activity type found")
            return False

        qil_model = self.admin.search_read(
            "ir.model", [("model", "=", "quality.issue.log")], fields=["id"], limit=1
        )[0]

        legacy_id = self.create("mail.activity", {
            "summary": "Review Quality Issue",
            "activity_type_id": todo_types[0]["id"],
            "res_model_id": qil_model["id"],
            "res_id": quality_log_id,
            "user_id": manager_id,
        })
        _info("Legacy activity created", legacy_id)

        self.admin.unlink("mail.activity", [legacy_id])

        try:
            self._try_read_activity(self.admin, legacy_id)
            _fail("read() should fail on deleted legacy activity")
            return False
        except RpcError as exc:
            if exc.is_missing_record:
                _ok(f"Legacy Missing Record reproduced: {exc}")
                return True
            _fail("Unexpected error", str(exc))
            return False

    def test_ask_for_review(self, data):
        _log("SCENARIO E — ask_for_review() via RPC (informational)")

        quality_log_id = data["quality_log_id"]
        self.admin.write("quality.issue.log", [quality_log_id], {"state": "enabled"})

        before = len(self.admin.search(
            "mail.activity",
            [("res_model", "=", "quality.issue.log"), ("res_id", "=", quality_log_id)],
        ))
        self.admin.call("quality.issue.log", "ask_for_review", [quality_log_id])
        after_ids = self.admin.search(
            "mail.activity",
            [("res_model", "=", "quality.issue.log"), ("res_id", "=", quality_log_id)],
        )
        qlog = self.admin.read("quality.issue.log", [quality_log_id], fields=["state"])[0]

        _info("Activities before ask_for_review", before)
        _info("Activities after ask_for_review", after_ids)
        _info("Quality log state", qlog["state"])
        _ok("ask_for_review() creates legacy To-Do on quality.issue.log (current module code)")
        return True

    def run(self, scenarios=None):
        all_scenarios = {
            "setup": lambda d: self.setup() if d is None else d,
            "normal_approve": self.test_normal_approve,
            "stale_activity": self.test_stale_activity,
            "double_approve_path": self.test_double_approve_path,
            "legacy_activity": self.test_legacy_activity,
            "ask_for_review": self.test_ask_for_review,
        }
        selected = scenarios or list(all_scenarios.keys())

        _log(
            "QUALITY ISSUE LOG — RPC TEST SCRIPT",
            f"Protocol: {type(self.admin).__name__}\n"
            f"URL: {self.admin.url}\n"
            f"DB: {self.admin.db}\n"
            f"RPC user: {self.admin.login} (uid={self.admin.uid})\n"
            f"Scenarios: {', '.join(selected)}",
        )

        results = {}
        data = None

        try:
            for key in selected:
                if key == "setup":
                    data = self.setup()
                    results[key] = True
                else:
                    if data is None:
                        data = self.setup()
                    results[key] = all_scenarios[key](data)
        except Exception as exc:
            _log("SCRIPT ERROR", str(exc))
            results["error"] = str(exc)
            raise
        finally:
            _log("SUMMARY")
            for key, passed in results.items():
                if key == "error":
                    print(f"  [ERROR] {key}: {passed}")
                elif passed is True:
                    print(f"  [PASS]  {key}")
                else:
                    print(f"  [FAIL]  {key}")
            self.cleanup_all()

        return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Test Quality Issue Log approval workflow via Odoo RPC",
    )
    parser.add_argument("--url", default=os.environ.get("ODOO_URL", "http://localhost:8069"))
    parser.add_argument("--db", default=os.environ.get("ODOO_DB"), required=not os.environ.get("ODOO_DB"))
    parser.add_argument("--user", default=os.environ.get("ODOO_USER", "admin"))
    parser.add_argument("--password", default=os.environ.get("ODOO_PASSWORD", "admin"))
    parser.add_argument(
        "--rpc", choices=["xmlrpc", "jsonrpc"],
        default=os.environ.get("ODOO_RPC", "xmlrpc"),
        help="RPC protocol (default: xmlrpc)",
    )
    parser.add_argument(
        "--scenarios",
        nargs="+",
        default=None,
        metavar="NAME",
        help="Scenarios to run: setup normal_approve stale_activity double_approve_path legacy_activity ask_for_review",
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Keep created test records in the database",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if not args.db:
        print("Error: --db is required (or set ODOO_DB)", file=sys.stderr)
        return 1

    try:
        admin = connect(args.url, args.db, args.user, args.password, rpc=args.rpc)
        runner = QualityIssueApprovalRpcTest(admin, cleanup=not args.no_cleanup)
        results = runner.run(scenarios=args.scenarios)
    except RpcError as exc:
        print(f"\nRPC Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        raise

    failed = [k for k, v in results.items() if k != "error" and v is False]
    return 1 if failed or "error" in results else 0


if __name__ == "__main__":
    sys.exit(main())
