#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone RPC test for cap_hr_skill (Odoo 19).

No odoo-bin / shell required. Run with plain Python 3:

    python3 scripts/test_cap_hr_skill_rpc.py
    python3 scripts/test_cap_hr_skill_rpc.py --protocol xmlrpc
    python3 scripts/test_cap_hr_skill_rpc.py --url http://localhost:8069 --db odoo --user admin --password admin

Environment variables (optional instead of flags):
  ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD, ODOO_RPC

Requirements on the Odoo server:
  - cap_hr_skill installed (depends on hr, hr_skills, mail, survey)
  - RPC user (default: admin) with rights to create employees, skills, validation requests

Tests custom fields and workflows via public RPC APIs using exact model/field names from:
  - models/hr_skill_inherit.py
  - models/hr_domain_skill.py
  - models/hr_skill_validator.py
  - models/skill_validation_request.py
  - models/employee.py
  - models/hr_employee_skill.py
  - models/res_company.py
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

# ---------------------------------------------------------------------------
# Configuration (override via CLI args)
# ---------------------------------------------------------------------------
DEFAULT_URL = "http://localhost:8069"
DEFAULT_DB = "odoo"
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "admin"
DEFAULT_PROTOCOL = "jsonrpc"  # jsonrpc | xmlrpc

MODULE_NAME = "cap_hr_skill"

# ---------------------------------------------------------------------------
# Technical names from models/hr_domain_skill.py
# ---------------------------------------------------------------------------
MODEL_DOMAIN_SKILL = "hr.domain.skill"
FIELD_DOMAIN_NAME = "name"
FIELD_DOMAIN_SKILL_TYPE = "skill_type_id"

# ---------------------------------------------------------------------------
# Technical names from models/hr_skill_inherit.py
# ---------------------------------------------------------------------------
MODEL_SKILL = "hr.skill"
MODEL_SKILL_TYPE = "hr.skill.type"
MODEL_SKILL_LEVEL = "hr.skill.level"
FIELD_SKILL_POINTS = "points"
FIELD_SKILL_VALIDATION_TYPE = "type_of_valivation"
FIELD_SKILL_DOMAIN = "domain_skill_id"
FIELD_SKILL_SURVEY = "survey_id"
FIELD_SKILL_TYPE_IS_FUNCTIONAL = "is_functional"

# ---------------------------------------------------------------------------
# Technical names from models/hr_skill_validator.py
# ---------------------------------------------------------------------------
MODEL_SKILL_VALIDATOR = "hr.skill.validator"
FIELD_VALIDATOR_USER = "validator_id"
FIELD_VALIDATOR_DOMAIN = "domain_skill_id"
FIELD_VALIDATOR_COMPANIES = "companies_ids"

# ---------------------------------------------------------------------------
# Technical names from models/skill_validation_request.py
# ---------------------------------------------------------------------------
MODEL_VALIDATION_REQUEST = "hr.skill.validation.request"
FIELD_REQUEST_EMPLOYEE = "employee_id"
FIELD_REQUEST_STATUS = "status"
FIELD_REQUEST_SKILL = "skill_id"
FIELD_REQUEST_VALIDATOR = "validator_id"
FIELD_REQUEST_TYPE = "type_of_valivation"

# ---------------------------------------------------------------------------
# Technical names from models/employee.py
# ---------------------------------------------------------------------------
MODEL_EMPLOYEE = "hr.employee"
FIELD_FUNCTIONAL_SCORE = "functional_knowledge_score"
FIELD_GLOBAL_SCORE = "global_knowledge_score"

# ---------------------------------------------------------------------------
# Technical names from models/hr_employee_skill.py
# ---------------------------------------------------------------------------
MODEL_EMPLOYEE_SKILL = "hr.employee.skill"
FIELD_EMPLOYEE_SKILL_DATE = "skill_date"

# ---------------------------------------------------------------------------
# Technical names from models/res_company.py
# ---------------------------------------------------------------------------
MODEL_COMPANY = "res.company"
FIELD_COMPANY_LIMITATION = "limitation_of_skill_request"


class RpcError(RuntimeError):
    """Odoo RPC fault / JSON-RPC error wrapper."""

    @property
    def is_validation_error(self) -> bool:
        msg = str(self).lower()
        return "validationerror" in msg or "cannot request" in msg or "already exists" in msg


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
                raise RpcError(
                    "Authentication failed. Check URL, database, username, and password."
                )
            self.uid = uid
            return uid

        uid = self._jsonrpc(
            "common", "authenticate", [self.db, self.username, self.password, {}]
        )
        if not uid:
            raise RpcError(
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
            raise RpcError("Not authenticated. Call authenticate() first.")
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

    def read(self, model: str, ids: list[int], fields: list[str]) -> list[dict]:
        return self.execute_kw(model, "read", [ids, fields])

    def create(self, model: str, vals: dict) -> int:
        return self.execute_kw(model, "create", [vals])

    def write(self, model: str, ids: list[int], vals: dict) -> bool:
        return self.execute_kw(model, "write", [ids, vals])

    def unlink(self, model: str, ids: list[int]) -> bool:
        return self.execute_kw(model, "unlink", [ids])

    def fields_get(self, model: str, fields: list[str] | None = None) -> dict:
        return self.execute_kw(model, "fields_get", [fields or []], {})

    def call(self, model: str, method: str, ids: list[int], kwargs: dict | None = None) -> Any:
        return self.execute_kw(model, method, [ids], kwargs or {})


class CapHrSkillRPCTest:
    """End-to-end cap_hr_skill workflow test via RPC."""

    def __init__(self, client: OdooRPCClient, cleanup: bool = True):
        self.client = client
        self.cleanup = cleanup
        self.passed = 0
        self.failed = 0
        self.suffix = datetime.now().strftime("%Y%m%d%H%M%S")
        self._cleanup_ids: dict[str, list[int]] = {
            MODEL_VALIDATION_REQUEST: [],
            MODEL_EMPLOYEE_SKILL: [],
            MODEL_EMPLOYEE: [],
            MODEL_SKILL_VALIDATOR: [],
            MODEL_SKILL: [],
            MODEL_SKILL_LEVEL: [],
            MODEL_DOMAIN_SKILL: [],
            MODEL_SKILL_TYPE: [],
        }
        self._ctx: dict[str, int] = {}

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
        if model in self._cleanup_ids:
            self._cleanup_ids[model].append(record_id)

    def _module_installed(self) -> bool:
        module_ids = self.client.search(
            "ir.module.module",
            [("name", "=", MODULE_NAME), ("state", "=", "installed")],
        )
        return bool(module_ids)

    def _field_exists(self, model: str, field_name: str) -> bool:
        fields = self.client.fields_get(model, [field_name])
        return field_name in fields

    def _get_company_id(self) -> int:
        users = self.client.read("res.users", [self.client.uid], ["company_id"])
        return self._m2o_id(users[0]["company_id"])

    def _setup_test_data(self) -> None:
        """Create skill type, domain, skills, validator, and employee for workflow tests."""
        company_id = self._get_company_id()

        skill_type_id = self.client.create(
            MODEL_SKILL_TYPE,
            {
                "name": f"RPC Skill Type {self.suffix}",
                FIELD_SKILL_TYPE_IS_FUNCTIONAL: True,
            },
        )
        self._track(MODEL_SKILL_TYPE, skill_type_id)

        skill_level_id = self.client.create(
            MODEL_SKILL_LEVEL,
            {
                "name": f"RPC Level {self.suffix}",
                "level_progress": 50,
                "skill_type_id": skill_type_id,
                "default_level": True,
            },
        )
        self._track(MODEL_SKILL_LEVEL, skill_level_id)

        domain_id = self.client.create(
            MODEL_DOMAIN_SKILL,
            {
                FIELD_DOMAIN_NAME: f"RPC Domain {self.suffix}",
                FIELD_DOMAIN_SKILL_TYPE: skill_type_id,
            },
        )
        self._track(MODEL_DOMAIN_SKILL, domain_id)

        skill_kb_id = self.client.create(
            MODEL_SKILL,
            {
                "name": f"RPC Knowledge Board {self.suffix}",
                "skill_type_id": skill_type_id,
                FIELD_SKILL_POINTS: 10,
                FIELD_SKILL_VALIDATION_TYPE: "knowledge_board",
                FIELD_SKILL_DOMAIN: domain_id,
            },
        )
        self._track(MODEL_SKILL, skill_kb_id)

        skill_fail_id = self.client.create(
            MODEL_SKILL,
            {
                "name": f"RPC Fail Skill {self.suffix}",
                "skill_type_id": skill_type_id,
                FIELD_SKILL_POINTS: 5,
                FIELD_SKILL_VALIDATION_TYPE: "recording",
                FIELD_SKILL_DOMAIN: domain_id,
            },
        )
        self._track(MODEL_SKILL, skill_fail_id)

        validator_record_id = self.client.create(
            MODEL_SKILL_VALIDATOR,
            {
                FIELD_VALIDATOR_USER: self.client.uid,
                FIELD_VALIDATOR_DOMAIN: domain_id,
                FIELD_VALIDATOR_COMPANIES: [(6, 0, [company_id])],
            },
        )
        self._track(MODEL_SKILL_VALIDATOR, validator_record_id)

        employee_id = self.client.create(
            MODEL_EMPLOYEE,
            {
                "name": f"RPC Test Employee {self.suffix}",
                "company_id": company_id,
            },
        )
        self._track(MODEL_EMPLOYEE, employee_id)

        self._ctx.update(
            {
                "company_id": company_id,
                "skill_type_id": skill_type_id,
                "skill_level_id": skill_level_id,
                "domain_id": domain_id,
                "skill_kb_id": skill_kb_id,
                "skill_fail_id": skill_fail_id,
                "validator_user_id": self.client.uid,
                "validator_record_id": validator_record_id,
                "employee_id": employee_id,
            }
        )

    def _create_validation_request(self, skill_id: int) -> int:
        request_id = self.client.create(
            MODEL_VALIDATION_REQUEST,
            {
                FIELD_REQUEST_EMPLOYEE: self._ctx["employee_id"],
                FIELD_REQUEST_SKILL: skill_id,
                FIELD_REQUEST_VALIDATOR: self._ctx["validator_user_id"],
            },
        )
        self._track(MODEL_VALIDATION_REQUEST, request_id)
        return request_id

    def _read_request(self, request_id: int, fields: list[str] | None = None) -> dict:
        return self.client.read(
            MODEL_VALIDATION_REQUEST,
            [request_id],
            fields or [FIELD_REQUEST_STATUS, FIELD_REQUEST_TYPE, FIELD_REQUEST_SKILL],
        )[0]

    def test_module_and_fields(self) -> None:
        self._ok(f"Module {MODULE_NAME!r} installed", self._module_installed())

        field_checks = [
            (MODEL_SKILL, FIELD_SKILL_POINTS),
            (MODEL_SKILL, FIELD_SKILL_VALIDATION_TYPE),
            (MODEL_SKILL, FIELD_SKILL_DOMAIN),
            (MODEL_SKILL, FIELD_SKILL_SURVEY),
            (MODEL_SKILL_TYPE, FIELD_SKILL_TYPE_IS_FUNCTIONAL),
            (MODEL_DOMAIN_SKILL, FIELD_DOMAIN_NAME),
            (MODEL_SKILL_VALIDATOR, FIELD_VALIDATOR_USER),
            (MODEL_VALIDATION_REQUEST, FIELD_REQUEST_STATUS),
            (MODEL_VALIDATION_REQUEST, FIELD_REQUEST_TYPE),
            (MODEL_EMPLOYEE, FIELD_FUNCTIONAL_SCORE),
            (MODEL_EMPLOYEE, FIELD_GLOBAL_SCORE),
            (MODEL_EMPLOYEE_SKILL, FIELD_EMPLOYEE_SKILL_DATE),
            (MODEL_COMPANY, FIELD_COMPANY_LIMITATION),
        ]
        for model, field in field_checks:
            self._ok(f"{model}.{field} field exists", self._field_exists(model, field))

    def test_domain_skill_crud(self) -> None:
        domain_data = self.client.read(
            MODEL_DOMAIN_SKILL,
            [self._ctx["domain_id"]],
            [FIELD_DOMAIN_NAME, FIELD_DOMAIN_SKILL_TYPE],
        )[0]
        self._ok(
            f"{MODEL_DOMAIN_SKILL} create/read",
            domain_data[FIELD_DOMAIN_NAME] == f"RPC Domain {self.suffix}",
            f"id={self._ctx['domain_id']}",
        )
        self._ok(
            f"{MODEL_DOMAIN_SKILL}.{FIELD_DOMAIN_SKILL_TYPE} link",
            self._m2o_id(domain_data[FIELD_DOMAIN_SKILL_TYPE]) == self._ctx["skill_type_id"],
        )

    def test_skill_validator(self) -> None:
        validator_data = self.client.read(
            MODEL_SKILL_VALIDATOR,
            [self._ctx["validator_record_id"]],
            [FIELD_VALIDATOR_USER, FIELD_VALIDATOR_DOMAIN],
        )[0]
        self._ok(
            f"{MODEL_SKILL_VALIDATOR}.{FIELD_VALIDATOR_USER} assigned",
            self._m2o_id(validator_data[FIELD_VALIDATOR_USER]) == self._ctx["validator_user_id"],
        )
        self._ok(
            f"{MODEL_SKILL_VALIDATOR}.{FIELD_VALIDATOR_DOMAIN} link",
            self._m2o_id(validator_data[FIELD_VALIDATOR_DOMAIN]) == self._ctx["domain_id"],
        )

    def test_validation_request_success_workflow(self) -> None:
        request_id = self._create_validation_request(self._ctx["skill_kb_id"])
        request = self._read_request(request_id)

        self._ok(
            f"{MODEL_VALIDATION_REQUEST} created with status 'requested'",
            request[FIELD_REQUEST_STATUS] == "requested",
            f"id={request_id}",
        )
        self._ok(
            f"{MODEL_VALIDATION_REQUEST}.{FIELD_REQUEST_TYPE} related from skill",
            request[FIELD_REQUEST_TYPE] == "knowledge_board",
        )

        self.client.call(MODEL_VALIDATION_REQUEST, "action_scheduled", [request_id])
        request = self._read_request(request_id, [FIELD_REQUEST_STATUS])
        self._ok(
            "action_scheduled() sets status to 'scheduled'",
            request[FIELD_REQUEST_STATUS] == "scheduled",
        )

        self.client.call(MODEL_VALIDATION_REQUEST, "action_success", [request_id])
        request = self._read_request(request_id, [FIELD_REQUEST_STATUS])
        self._ok(
            "action_success() sets status to 'succeed'",
            request[FIELD_REQUEST_STATUS] == "succeed",
        )

        employee_skill_ids = self.client.search(
            MODEL_EMPLOYEE_SKILL,
            [
                ("employee_id", "=", self._ctx["employee_id"]),
                ("skill_id", "=", self._ctx["skill_kb_id"]),
            ],
        )
        self._ok(
            "action_success() creates hr.employee.skill",
            bool(employee_skill_ids),
            f"employee_skill ids={employee_skill_ids}",
        )
        if employee_skill_ids:
            self._track(MODEL_EMPLOYEE_SKILL, employee_skill_ids[0])
            skill_row = self.client.read(
                MODEL_EMPLOYEE_SKILL,
                [employee_skill_ids[0]],
                [FIELD_EMPLOYEE_SKILL_DATE],
            )[0]
            self._ok(
                f"{MODEL_EMPLOYEE_SKILL}.{FIELD_EMPLOYEE_SKILL_DATE} set",
                bool(skill_row.get(FIELD_EMPLOYEE_SKILL_DATE)),
            )

    def test_validation_request_failed_workflow(self) -> None:
        request_id = self._create_validation_request(self._ctx["skill_fail_id"])
        self.client.call(MODEL_VALIDATION_REQUEST, "action_failed", [request_id])
        request = self._read_request(request_id, [FIELD_REQUEST_STATUS])
        self._ok(
            "action_failed() sets status to 'failed'",
            request[FIELD_REQUEST_STATUS] == "failed",
        )

    def test_duplicate_skill_constraint(self) -> None:
        """Employee already has the skill after success — new request must be rejected."""
        rejected = False
        try:
            self._create_validation_request(self._ctx["skill_kb_id"])
        except RpcError as exc:
            rejected = exc.is_validation_error
            self._ok(
                "Duplicate skill validation request rejected",
                rejected,
                str(exc),
            )
        if not rejected:
            self._ok("Duplicate skill validation request rejected", False, "no ValidationError raised")

    def test_employee_knowledge_scores(self) -> None:
        employee = self.client.read(
            MODEL_EMPLOYEE,
            [self._ctx["employee_id"]],
            [FIELD_FUNCTIONAL_SCORE, FIELD_GLOBAL_SCORE],
        )[0]
        self._ok(
            f"{MODEL_EMPLOYEE}.{FIELD_FUNCTIONAL_SCORE} computed after skill success",
            employee[FIELD_FUNCTIONAL_SCORE] >= 10,
            f"score={employee[FIELD_FUNCTIONAL_SCORE]}",
        )
        self._ok(
            f"{MODEL_EMPLOYEE}.{FIELD_GLOBAL_SCORE} computed after skill success",
            employee[FIELD_GLOBAL_SCORE] >= 10,
            f"score={employee[FIELD_GLOBAL_SCORE]}",
        )

    def test_company_limitation_field(self) -> None:
        company = self.client.read(
            MODEL_COMPANY,
            [self._ctx["company_id"]],
            [FIELD_COMPANY_LIMITATION],
        )[0]
        self._ok(
            f"{MODEL_COMPANY}.{FIELD_COMPANY_LIMITATION} readable",
            company[FIELD_COMPANY_LIMITATION] > 0,
            f"limit={company[FIELD_COMPANY_LIMITATION]}",
        )

    def _cleanup_records(self) -> None:
        if not self.cleanup:
            print("  [INFO] Cleanup skipped (--no-cleanup)")
            return

        order = [
            MODEL_VALIDATION_REQUEST,
            MODEL_EMPLOYEE_SKILL,
            MODEL_EMPLOYEE,
            MODEL_SKILL_VALIDATOR,
            MODEL_SKILL,
            MODEL_SKILL_LEVEL,
            MODEL_DOMAIN_SKILL,
            MODEL_SKILL_TYPE,
        ]
        for model in order:
            ids = self._cleanup_ids.get(model, [])
            if ids:
                try:
                    self.client.unlink(model, ids)
                    print(f"  Cleaned up {len(ids)} {model} record(s)")
                except RpcError as exc:
                    print(f"  [WARN] cleanup {model} {ids}: {exc}")
            self._cleanup_ids[model] = []

    def run(self) -> bool:
        print("=" * 80)
        print("Cap Hr Skill — RPC Test (Odoo 19)")
        print(f"Module : {MODULE_NAME}")
        print(
            f"Protocol: {self.client.protocol.upper()} | DB: {self.client.db} | URL: {self.client.url}"
        )
        print("=" * 80)

        try:
            self.test_module_and_fields()
            self._setup_test_data()
            self.test_domain_skill_crud()
            self.test_skill_validator()
            self.test_validation_request_success_workflow()
            self.test_validation_request_failed_workflow()
            self.test_duplicate_skill_constraint()
            self.test_employee_knowledge_scores()
            self.test_company_limitation_field()
        finally:
            print("=" * 80)
            print(f"Result: {self.passed} passed, {self.failed} failed")
            print("=" * 80)
            self._cleanup_records()

        return self.failed == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RPC test for cap_hr_skill (Odoo 19)",
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("ODOO_URL", DEFAULT_URL),
        help=f"Odoo URL (default: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("ODOO_DB", DEFAULT_DB),
        help=f"Database name (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--user",
        default=os.environ.get("ODOO_USER", DEFAULT_USER),
        help=f"Username (default: {DEFAULT_USER})",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("ODOO_PASSWORD", DEFAULT_PASSWORD),
        help="Password",
    )
    parser.add_argument(
        "--protocol",
        "--rpc",
        dest="protocol",
        choices=["jsonrpc", "xmlrpc"],
        default=os.environ.get("ODOO_RPC", DEFAULT_PROTOCOL),
        help=f"RPC protocol (default: {DEFAULT_PROTOCOL})",
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Keep created test records in the database",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = OdooRPCClient(args.url, args.db, args.user, args.password, args.protocol)
    try:
        uid = client.authenticate()
        print(f"Authenticated uid={uid}")
    except RpcError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    success = CapHrSkillRPCTest(client, cleanup=not args.no_cleanup).run()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
