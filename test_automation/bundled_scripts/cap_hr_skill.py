#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skill validation workflow test for cap_hr_skill via XML-RPC or JSON-RPC.

Simulates real users (employee + validator). Admin is used only to seed master
data and test accounts — no field/metadata checks.

    python3 scripts/test_cap_hr_skill_rpc.py --db YOUR_DB
    python3 scripts/test_cap_hr_skill_rpc.py --protocol xmlrpc --db YOUR_DB

Environment variables: ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD, ODOO_RPC
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import xmlrpc.client
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_URL = "http://localhost:8069"
DEFAULT_DB = "odoo"
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "admin"
DEFAULT_PROTOCOL = "jsonrpc"
DEFAULT_TEST_PASSWORD = "CapHrSkillTest123!"

MODEL_DOMAIN_SKILL = "hr.domain.skill"
MODEL_SKILL = "hr.skill"
MODEL_SKILL_TYPE = "hr.skill.type"
MODEL_SKILL_LEVEL = "hr.skill.level"
MODEL_SKILL_VALIDATOR = "hr.skill.validator"
MODEL_VALIDATION_REQUEST = "hr.skill.validation.request"
MODEL_EMPLOYEE = "hr.employee"
MODEL_EMPLOYEE_SKILL = "hr.employee.skill"


class RpcError(RuntimeError):
    @property
    def is_validation_error(self) -> bool:
        msg = str(self).lower()
        return (
            "validationerror" in msg
            or "cannot request" in msg
            or "already exists" in msg
        )


class OdooRPCClient:
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
                raise RpcError("Authentication failed.")
            self.uid = uid
            return uid

        uid = self._jsonrpc(
            "common", "authenticate", [self.db, self.username, self.password, {}]
        )
        if not uid:
            raise RpcError("Authentication failed.")
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
            raise RpcError(f"HTTP error {exc.code}: {exc.reason}") from exc
        except URLError as exc:
            raise RpcError(f"Cannot reach Odoo at {self.url}: {exc}") from exc

        if body.get("error"):
            err = body["error"]
            msg = err.get("data", {}).get("message") or err.get("message") or str(err)
            raise RpcError(f"Odoo RPC error: {msg}")
        return body.get("result")

    def execute_kw(
        self,
        model: str,
        method: str,
        args: list | None = None,
        kwargs: dict | None = None,
    ) -> Any:
        if self.uid is None:
            raise RpcError("Not authenticated.")
        args = args or []
        kwargs = kwargs or {}
        if self.protocol == "xmlrpc":
            try:
                return self._xml_models.execute_kw(
                    self.db, self.uid, self.password, model, method, args, kwargs
                )
            except xmlrpc.client.Fault as exc:
                raise RpcError(exc.faultString) from exc
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

    def call(self, model: str, method: str, ids: list[int]) -> Any:
        return self.execute_kw(model, method, [ids], {})


def connect(url: str, db: str, login: str, password: str, protocol: str) -> OdooRPCClient:
    client = OdooRPCClient(url, db, login, password, protocol)
    client.authenticate()
    return client


class CapHrSkillWorkflowTest:
    """Employee / validator skill validation workflow via RPC."""

    def __init__(self, admin: OdooRPCClient, cleanup: bool = True):
        self.admin = admin
        self.cleanup = cleanup
        self.passed = 0
        self.failed = 0
        self.suffix = datetime.now().strftime("%Y%m%d%H%M%S")
        self.test_password = DEFAULT_TEST_PASSWORD
        self._created: list[tuple[str, int]] = []

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

    def _track(self, model: str, record_id: int) -> None:
        self._created.append((model, record_id))

    def _create(self, model: str, vals: dict) -> int:
        record_id = self.admin.create(model, vals)
        self._track(model, record_id)
        return record_id

    def _user_client(self, login: str) -> OdooRPCClient:
        return connect(
            self.admin.url,
            self.admin.db,
            login,
            self.test_password,
            self.admin.protocol,
        )

    def _get_company_id(self) -> int:
        users = self.admin.read("res.users", [self.admin.uid], ["company_id"])
        return self._m2o_id(users[0]["company_id"])

    def _read_request(self, client: OdooRPCClient, request_id: int, fields: list[str]) -> dict:
        return client.read(MODEL_VALIDATION_REQUEST, [request_id], fields)[0]

    def setup(self) -> dict[str, Any]:
        """Admin seeds master data and creates employee + validator users."""
        print("\n--- SETUP (admin) ---")
        company_id = self._get_company_id()

        employee_login = f"cap_skill_emp_{self.suffix}@test.com"
        validator_login = f"cap_skill_val_{self.suffix}@test.com"

        employee_user_id = self._create("res.users", {
            "name": f"Skill Employee {self.suffix}",
            "login": employee_login,
            "password": self.test_password,
            "group_ids": [(6, 0, [self._xmlid_res_id("base.group_user")])],
            "company_id": company_id,
            "company_ids": [(6, 0, [company_id])],
        })
        validator_user_id = self._create("res.users", {
            "name": f"Skill Validator {self.suffix}",
            "login": validator_login,
            "password": self.test_password,
            "group_ids": [(6, 0, [self._xmlid_res_id("base.group_user")])],
            "company_id": company_id,
            "company_ids": [(6, 0, [company_id])],
        })

        employee_id = self._create(MODEL_EMPLOYEE, {
            "name": f"Skill Employee {self.suffix}",
            "user_id": employee_user_id,
            "company_id": company_id,
        })
        self._create(MODEL_EMPLOYEE, {
            "name": f"Skill Validator {self.suffix}",
            "user_id": validator_user_id,
            "company_id": company_id,
        })

        skill_type_id = self._create(MODEL_SKILL_TYPE, {
            "name": f"RPC Skill Type {self.suffix}",
            "is_functional": True,
        })
        self._create(MODEL_SKILL_LEVEL, {
            "name": f"RPC Level {self.suffix}",
            "level_progress": 50,
            "skill_type_id": skill_type_id,
            "default_level": True,
        })
        domain_id = self._create(MODEL_DOMAIN_SKILL, {
            "name": f"RPC Domain {self.suffix}",
            "skill_type_id": skill_type_id,
        })

        skill_success_id = self._create(MODEL_SKILL, {
            "name": f"RPC Knowledge Board {self.suffix}",
            "skill_type_id": skill_type_id,
            "points": 10,
            "type_of_valivation": "knowledge_board",
            "domain_skill_id": domain_id,
        })
        skill_fail_id = self._create(MODEL_SKILL, {
            "name": f"RPC Recording {self.suffix}",
            "skill_type_id": skill_type_id,
            "points": 5,
            "type_of_valivation": "recording",
            "domain_skill_id": domain_id,
        })

        self._create(MODEL_SKILL_VALIDATOR, {
            "validator_id": validator_user_id,
            "domain_skill_id": domain_id,
            "companies_ids": [(6, 0, [company_id])],
        })

        print(f"  employee login : {employee_login}")
        print(f"  validator login: {validator_login}")

        return {
            "employee_login": employee_login,
            "validator_login": validator_login,
            "employee_id": employee_id,
            "skill_success_id": skill_success_id,
            "skill_fail_id": skill_fail_id,
            "validator_user_id": validator_user_id,
        }

    def _xmlid_res_id(self, xml_id: str) -> int:
        module, name = xml_id.split(".")
        rows = self.admin.search("ir.model.data", [
            ("module", "=", module),
            ("name", "=", name),
        ], limit=1)
        if not rows:
            raise RpcError(f"XML id not found: {xml_id}")
        return self.admin.read("ir.model.data", rows, ["res_id"])[0]["res_id"]

    def test_employee_submits_request(self, data: dict) -> int:
        """Employee creates a skill validation request."""
        print("\n--- WORKFLOW 1: employee submits request ---")
        employee = self._user_client(data["employee_login"])

        request_id = employee.create(MODEL_VALIDATION_REQUEST, {
            "employee_id": data["employee_id"],
            "skill_id": data["skill_success_id"],
            "validator_id": data["validator_user_id"],
        })
        self._track(MODEL_VALIDATION_REQUEST, request_id)

        request = self._read_request(employee, request_id, ["status", "type_of_valivation"])
        self._ok("Employee can create validation request", True, f"id={request_id}")
        self._ok("Initial status is 'requested'", request["status"] == "requested")
        self._ok(
            "Validation type comes from skill",
            request["type_of_valivation"] == "knowledge_board",
        )
        return request_id

    def test_validator_success_path(self, data: dict, request_id: int) -> None:
        """Validator schedules then approves; skill is added to employee."""
        print("\n--- WORKFLOW 2: validator schedules and approves ---")
        validator = self._user_client(data["validator_login"])

        validator.call(MODEL_VALIDATION_REQUEST, "action_scheduled", [request_id])
        request = self._read_request(validator, request_id, ["status"])
        self._ok("Validator action_scheduled() -> 'scheduled'", request["status"] == "scheduled")

        validator.call(MODEL_VALIDATION_REQUEST, "action_success", [request_id])
        request = self._read_request(validator, request_id, ["status"])
        self._ok("Validator action_success() -> 'succeed'", request["status"] == "succeed")

        employee_skill_ids = self.admin.search(MODEL_EMPLOYEE_SKILL, [
            ("employee_id", "=", data["employee_id"]),
            ("skill_id", "=", data["skill_success_id"]),
        ])
        self._ok(
            "Approved request adds skill on employee",
            bool(employee_skill_ids),
            f"employee_skill ids={employee_skill_ids}",
        )
        if employee_skill_ids:
            self._track(MODEL_EMPLOYEE_SKILL, employee_skill_ids[0])

        employee = self.admin.read(MODEL_EMPLOYEE, [data["employee_id"]], [
            "functional_knowledge_score",
            "global_knowledge_score",
        ])[0]
        self._ok(
            "Employee knowledge scores updated after approval",
            employee["functional_knowledge_score"] >= 10
            and employee["global_knowledge_score"] >= 10,
            f"functional={employee['functional_knowledge_score']}, "
            f"global={employee['global_knowledge_score']}",
        )

    def test_validator_failed_path(self, data: dict) -> None:
        """Employee submits another skill; validator rejects it."""
        print("\n--- WORKFLOW 3: employee submits, validator rejects ---")
        employee = self._user_client(data["employee_login"])
        validator = self._user_client(data["validator_login"])

        request_id = employee.create(MODEL_VALIDATION_REQUEST, {
            "employee_id": data["employee_id"],
            "skill_id": data["skill_fail_id"],
            "validator_id": data["validator_user_id"],
        })
        self._track(MODEL_VALIDATION_REQUEST, request_id)

        validator.call(MODEL_VALIDATION_REQUEST, "action_failed", [request_id])
        request = self._read_request(validator, request_id, ["status"])
        self._ok("Validator action_failed() -> 'failed'", request["status"] == "failed")

        employee_skill_ids = self.admin.search(MODEL_EMPLOYEE_SKILL, [
            ("employee_id", "=", data["employee_id"]),
            ("skill_id", "=", data["skill_fail_id"]),
        ])
        self._ok(
            "Rejected request does not add skill on employee",
            not employee_skill_ids,
        )

    def test_duplicate_request_blocked(self, data: dict) -> None:
        """Employee cannot re-request a skill they already have."""
        print("\n--- WORKFLOW 4: duplicate request blocked ---")
        employee = self._user_client(data["employee_login"])

        rejected = False
        try:
            request_id = employee.create(MODEL_VALIDATION_REQUEST, {
                "employee_id": data["employee_id"],
                "skill_id": data["skill_success_id"],
                "validator_id": data["validator_user_id"],
            })
            self._track(MODEL_VALIDATION_REQUEST, request_id)
        except RpcError as exc:
            rejected = exc.is_validation_error
            self._ok("Duplicate skill request rejected for employee", rejected, str(exc))

        if not rejected:
            self._ok("Duplicate skill request rejected for employee", False, "no error raised")

    def _cleanup_records(self) -> None:
        if not self.cleanup:
            print("\n[INFO] Cleanup skipped (--no-cleanup)")
            return

        print("\n--- CLEANUP (admin) ---")
        for model, record_id in reversed(self._created):
            try:
                if self.admin.search(model, [("id", "=", record_id)], limit=1):
                    self.admin.execute_kw(model, "unlink", [[record_id]])
                    print(f"  deleted {model}({record_id})")
            except RpcError as exc:
                print(f"  [WARN] could not delete {model}({record_id}): {exc}")

    def run(self) -> bool:
        print("=" * 72)
        print("Cap Hr Skill — workflow RPC test")
        print(
            f"Protocol: {self.admin.protocol.upper()} | "
            f"DB: {self.admin.db} | URL: {self.admin.url}"
        )
        print("=" * 72)

        try:
            data = self.setup()
            request_id = self.test_employee_submits_request(data)
            self.test_validator_success_path(data, request_id)
            self.test_validator_failed_path(data)
            self.test_duplicate_request_blocked(data)
        finally:
            print("=" * 72)
            print(f"Result: {self.passed} passed, {self.failed} failed")
            print("=" * 72)
            self._cleanup_records()

        return self.failed == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Workflow RPC test for cap_hr_skill (employee + validator)",
    )
    parser.add_argument("--url", default=os.environ.get("ODOO_URL", DEFAULT_URL))
    parser.add_argument("--db", default=os.environ.get("ODOO_DB", DEFAULT_DB))
    parser.add_argument("--user", default=os.environ.get("ODOO_USER", DEFAULT_USER))
    parser.add_argument("--password", default=os.environ.get("ODOO_PASSWORD", DEFAULT_PASSWORD))
    parser.add_argument(
        "--protocol", "--rpc",
        dest="protocol",
        choices=["jsonrpc", "xmlrpc"],
        default=os.environ.get("ODOO_RPC", DEFAULT_PROTOCOL),
    )
    parser.add_argument("--no-cleanup", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        admin = connect(args.url, args.db, args.user, args.password, args.protocol)
        print(f"Authenticated admin uid={admin.uid}")
    except RpcError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    success = CapHrSkillWorkflowTest(admin, cleanup=not args.no_cleanup).run()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
