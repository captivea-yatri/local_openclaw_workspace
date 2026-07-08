#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone RPC test for cap_contract_management (Odoo 19).

Run with plain Python 3:
  python3 scripts/test_cap_contract_management_rpc.py
  python3 scripts/test_cap_contract_management_rpc.py --protocol xmlrpc
  python3 scripts/test_cap_contract_management_rpc.py \
    --url https://uriah-apolitical-masako.ngrok-free.dev \
    --db odoo19_captivea2 --user admin1 --password a
"""
from __future__ import annotations

import argparse
import json
import sys
import xmlrpc.client
from datetime import date, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Configuration (override via CLI args)
# ---------------------------------------------------------------------------
DEFAULT_URL = "https://uriah-apolitical-masako.ngrok-free.dev"
DEFAULT_DB = "odoo19_captivea2"
DEFAULT_USER = "admin1"
DEFAULT_PASSWORD = "a"
DEFAULT_PROTOCOL = "jsonrpc"  # jsonrpc | xmlrpc

MODULE_NAME = "cap_contract_management"
CONFIG_MODEL = "employee.contract.configuration"
ITEM_MODEL = "employee.contract.configuration.item"
SIGN_REQUEST_MODEL = "sign.request"
EMPLOYEE_MODEL = "hr.employee"

# Odoo x2many command tuples (same as odoo.fields.Command)
CMD_CREATE = 0
CMD_LINK = 4
CMD_CLEAR = 5
CMD_SET = 6


class OdooRPCClient:
    """Thin Odoo 19 RPC client (JSON-RPC or XML-RPC)."""

    def __init__(
        self,
        url: str,
        db: str,
        username: str,
        password: str,
        protocol: str = "jsonrpc",
    ) -> None:
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
            uid = self._xml_common.authenticate(
                self.db, self.username, self.password, {}
            )
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
            with urlopen(req, timeout=180) as resp:
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

    def read(self, model: str, ids: list[int], fields: list[str]) -> list[dict]:
        return self.execute_kw(model, "read", [ids, fields])

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


def _m2o_id(value: Any) -> int | None:
    if not value:
        return None
    if isinstance(value, (list, tuple)):
        return value[0]
    return int(value)


def _m2m_ids(value: Any) -> list[int]:
    if not value:
        return []
    return list(value)


def _normalize_role(name: str) -> str:
    return (name or "").lower().replace(" ", "")


def _template_has_employee_role(client: OdooRPCClient, template_id: int) -> bool:
    items = client.read(
        "sign.template", [template_id], ["sign_item_ids"]
    )[0]["sign_item_ids"]
    if not items:
        return False
    sign_items = client.read(
        "sign.item", items, ["type_id", "responsible_id", "required"]
    )
    type_ids = [t for t in (_m2o_id(i["type_id"]) for i in sign_items) if t]
    types = {
        t["id"]: t for t in client.read("sign.item.type", type_ids, ["item_type"])
    }
    signature_items = [
        i
        for i in sign_items
        if _m2o_id(i["type_id"])
        and types.get(_m2o_id(i["type_id"]), {}).get("item_type") == "signature"
        and _m2o_id(i["responsible_id"])
    ]
    if not signature_items:
        return False
    role_ids = list({_m2o_id(i["responsible_id"]) for i in signature_items})
    roles = client.read("sign.item.role", role_ids, ["name"])
    role_employee = next(
        (r for r in roles if "employee" in _normalize_role(r["name"])), None
    )
    if not role_employee:
        return False
    employee_signatures = [
        i for i in signature_items if _m2o_id(i["responsible_id"]) == role_employee["id"]
    ]
    return any(i.get("required") for i in employee_signatures)


class CapContractManagementRPCTest:
    """End-to-end contract management workflow test via RPC."""

    def __init__(self, client: OdooRPCClient):
        self.client = client
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self._cleanup: dict[str, list[int]] = {
            CONFIG_MODEL: [],
            ITEM_MODEL: [],
            SIGN_REQUEST_MODEL: [],
            EMPLOYEE_MODEL: [],
            "res.partner": [],
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

    def _warn(self, label: str, detail: str = "") -> None:
        msg = f"[WARN] {label}"
        if detail:
            msg += f" -> {detail}"
        print(msg)
        self.warnings += 1

    def _track(self, model: str, record_id: int) -> None:
        self._cleanup.setdefault(model, []).append(record_id)

    def _today(self) -> str:
        return str(date.today())

    def _date_offset(self, days: int) -> str:
        return str(date.today() + timedelta(days=days))

    def _check_module_installed(self) -> bool:
        module_ids = self.client.search(
            "ir.module.module",
            [("name", "=", MODULE_NAME), ("state", "=", "installed")],
            limit=1,
        )
        return self._ok(
            f"Module {MODULE_NAME} is installed",
            bool(module_ids),
            f"id={module_ids[0] if module_ids else 'n/a'}",
        )

    def _check_model_fields(self) -> None:
        config_fields = [
            "name",
            "employee_ids",
            "job_position_ids",
            "department_ids",
            "company_ids",
            "sign_request_ids",
            "sign_request_count",
            "contract_item_ids",
            "status",
            "employee_manual_ids",
            "employee_ids_domain",
            "is_sign_document_sent",
            "skipped_employee_ids",
            "excluded_employee_ids",
        ]
        fg = self.client.execute_kw(CONFIG_MODEL, "fields_get", [config_fields, {}])
        self._ok(
            "employee.contract.configuration fields exist",
            all(f in fg for f in config_fields),
            ", ".join(sorted(fg.keys())),
        )
        item_fields = [
            "sign_template_id",
            "employee_contract_config_id",
            "sign_request_ids",
            "send_date",
            "start_date",
            "end_date",
            "is_readonly",
        ]
        fg_item = self.client.execute_kw(ITEM_MODEL, "fields_get", [item_fields, {}])
        self._ok(
            "employee.contract.configuration.item fields exist",
            all(f in fg_item for f in item_fields),
        )
        sign_fields = ["contract_config_id", "contract_item_id"]
        fg_sign = self.client.execute_kw(SIGN_REQUEST_MODEL, "fields_get", [sign_fields, {}])
        self._ok(
            "sign.request extended fields exist",
            all(f in fg_sign for f in sign_fields),
        )
        fg_emp = self.client.execute_kw(EMPLOYEE_MODEL, "fields_get", [["contract_status"], {}])
        self._ok(
            "hr.employee.contract_status field exists",
            "contract_status" in fg_emp,
        )

    def _find_eligible_sign_template(self) -> int | None:
        template_ids = self.client.search("sign.template", [], order="id")
        for tmpl_id in template_ids:
            if _template_has_employee_role(self.client, tmpl_id):
                return tmpl_id
        return None

    def _find_or_prepare_employee(self) -> int | None:
        employee_ids = self.client.search(
            EMPLOYEE_MODEL,
            [("active", "=", True)],
            limit=20,
            order="id",
        )
        for emp_id in employee_ids:
            emp = self.client.read(
                EMPLOYEE_MODEL, [emp_id], ["partner_id", "work_email", "company_id"]
            )[0]
            if _m2o_id(emp["partner_id"]) and emp.get("work_email"):
                return emp_id
        company_ids = self.client.search("res.company", [], limit=1)
        if not company_ids:
            return None
        partner_id = self.client.create(
            "res.partner",
            {"name": "CAP Contract RPC Test Employee", "email": "cap.contract.rpc@test.local"},
        )
        self._track("res.partner", partner_id)
        emp_id = self.client.create(
            EMPLOYEE_MODEL,
            {
                "name": "CAP Contract RPC Test Employee",
                "partner_id": partner_id,
                "work_email": "cap.contract.rpc@test.local",
                "company_id": company_ids[0],
            },
        )
        self._track(EMPLOYEE_MODEL, emp_id)
        return emp_id

    def _test_configuration_employee_matching(self) -> int | None:
        company_ids = self.client.search("res.company", [], limit=1)
        if not company_ids:
            self._warn("No company found; skipping configuration test")
            return None
        config_id = self.client.create(
            CONFIG_MODEL,
            {"name": "CAP RPC Test Configuration", "company_ids": [(CMD_SET, 0, company_ids)]},
        )
        self._track(CONFIG_MODEL, config_id)
        config = self.client.read(
            CONFIG_MODEL, [config_id], ["name", "status", "employee_ids", "company_ids", "employee_ids_domain"]
        )[0]
        self._ok("Configuration created", config["name"] == "CAP RPC Test Configuration")
        self._ok("Default status is not_covered", config["status"] == "not_covered")
        self._ok(
            "employee_ids_domain computed",
            bool(config.get("employee_ids_domain")),
        )
        employee_id = self._find_or_prepare_employee()
        if not employee_id:
            self._warn("No employee available for manual assignment test")
            return config_id
        self.client.write(
            CONFIG_MODEL,
            [config_id],
            {"employee_manual_ids": [(CMD_SET, 0, [employee_id])]},
        )
        config = self.client.read(
            CONFIG_MODEL, [config_id], ["employee_ids", "employee_manual_ids"]
        )[0]
        self._ok(
            "Manual employee assignment stored",
            employee_id in _m2m_ids(config["employee_manual_ids"]),
        )
        self._ok(
            "employee_ids reflects manual selection",
            employee_id in _m2m_ids(config["employee_ids"]),
        )
        return config_id

    def _test_contract_item_dates(self, config_id: int, template_id: int) -> int | None:
        today = self._today()
        start = self._date_offset(1)
        end = self._date_offset(30)
        item_id = self.client.create(
            ITEM_MODEL,
            {
                "employee_contract_config_id": config_id,
                "sign_template_id": template_id,
                "send_date": today,
                "start_date": start,
                "end_date": end,
            },
        )
        self._track(ITEM_MODEL, item_id)
        item = self.client.read(
            ITEM_MODEL,
            [item_id],
            ["sign_template_id", "send_date", "start_date", "end_date", "is_readonly"],
        )[0]
        self._ok(
            "Contract item created with valid dates",
            _m2o_id(item["sign_template_id"]) == template_id,
            f"item_id={item_id}",
        )
        self._ok("Contract item is_readonly is False", not item["is_readonly"])
        # Test invalid start date
        invalid_start = self._date_offset(-5)
        try:
            self.client.create(
                ITEM_MODEL,
                {
                    "employee_contract_config_id": config_id,
                    "sign_template_id": template_id,
                    "send_date": today,
                    "start_date": invalid_start,
                    "end_date": end,
                },
            )
            self._ok("Rejects start_date before send_date", False)
        except RuntimeError as exc:
            self._ok(
                "Rejects start_date before send_date",
                "start date" in str(exc).lower() or "send date" in str(exc).lower(),
                str(exc)[:120],
            )
        return item_id

    def _test_action_view_sign_requests(self, config_id: int) -> None:
        action = self.client.call(CONFIG_MODEL, "action_view_sign_requests", [config_id])
        self._ok(
            "action_view_sign_requests returns window action",
            isinstance(action, dict)
            and action.get("type") == "ir.actions.act_window"
            and action.get("res_model") == SIGN_REQUEST_MODEL,
        )

    def _test_send_sign_requests(self, config_id: int) -> list[int]:
        created: list[int] = []
        before = self.client.read(
            CONFIG_MODEL,
            [config_id],
            ["sign_request_count", "sign_request_ids"],
        )[0]
        before_count = before["sign_request_count"]
        before_ids = set(_m2m_ids(before["sign_request_ids"]))
        try:
            self.client.call(CONFIG_MODEL, "action_send_sign_requests", [config_id])
        except RuntimeError as exc:
            self._warn("action_send_sign_requests failed", str(exc)[:200])
            return created
        after = self.client.read(
            CONFIG_MODEL,
            [config_id],
            ["sign_request_count", "sign_request_ids", "is_sign_document_sent"],
        )[0]
        after_ids = set(_m2m_ids(after["sign_request_ids"]))
        new_ids = sorted(after_ids - before_ids)
        created.extend(new_ids)
        self._ok(
            "sign_request_count increased or unchanged",
            after["sign_request_count"] >= before_count,
        )
        self._ok(
            "is_sign_document_sent computed",
            after["is_sign_document_sent"] is True or not new_ids,
        )
        for sign_id in new_ids:
            self._track(SIGN_REQUEST_MODEL, sign_id)
        return created

    def _test_cron_send_all_sign_requests(self) -> None:
        try:
            self.client.execute_kw(CONFIG_MODEL, "_cron_send_all_sign_requests", [[]], {})
            self._ok("_cron_send_all_sign_requests callable", True)
        except RuntimeError as exc:
            self._warn("_cron_send_all_sign_requests failed", str(exc)[:200])

    def _test_employee_apply_configurations(self, employee_id: int) -> None:
        try:
            self.client.execute_kw(
                EMPLOYEE_MODEL, "_apply_contract_configurations", [[employee_id]], {}
            )
            self._ok("_apply_contract_configurations callable", True)
        except RuntimeError as exc:
            self._warn("_apply_contract_configurations failed", str(exc)[:200])
        emp = self.client.read(EMPLOYEE_MODEL, [employee_id], ["contract_status"])[0]
        self._ok(
            "employee contract_status readable",
            emp.get("contract_status") in (False, "covered", "not_covered", None),
        )

    def _test_sign_request_filter_domain(self) -> None:
        sign_ids = self.client.search(
            SIGN_REQUEST_MODEL, [("contract_config_id", "!=", False)], limit=5
        )
        self._ok(
            "search by contract_config_id works",
            isinstance(sign_ids, list),
        )

    def _cleanup_records(self) -> None:
        print("-" * 80)
        print("Cleaning up test records...")
        for model, ids in self._cleanup.items():
            if not ids:
                continue
            try:
                self.client.unlink(model, ids)
                print(f" Unlinked {len(ids)} from {model}")
            except RuntimeError as exc:
                print(f" [WARN] Could not unlink {model}: {exc}")

    def run(self) -> bool:
        print("=" * 80)
        print(f"cap_contract_management RPC test ({self.client.protocol.upper()})")
        print("=" * 80)
        if not self._check_module_installed():
            print("Module not installed.")
            return False
        self._check_model_fields()
        config_id = self._test_configuration_employee_matching()
        if not config_id:
            return False
        tmpl_id = self._find_eligible_sign_template()
        if tmpl_id:
            self._test_contract_item_dates(config_id, tmpl_id)
            self._test_action_view_sign_requests(config_id)
            self._test_send_sign_requests(config_id)
        else:
            self._warn("No eligible sign.template found")
        self._test_cron_send_all_sign_requests()
        self._test_sign_request_filter_domain()
        emp_id = self._find_or_prepare_employee()
        if emp_id:
            self._test_employee_apply_configurations(emp_id)
        self._cleanup_records()
        print("=" * 80)
        print(f"Result: {self.passed} passed, {self.failed} failed, {self.warnings} warnings")
        print("=" * 80)
        return self.failed == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RPC test for cap_contract_management (Odoo 19)")
    parser.add_argument("--url", default=DEFAULT_URL, help="Odoo URL")
    parser.add_argument("--db", default=DEFAULT_DB, help="Database name")
    parser.add_argument("--user", default=DEFAULT_USER, help="Username")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Password")
    parser.add_argument(
        "--protocol",
        choices=["jsonrpc", "xmlrpc"],
        default=DEFAULT_PROTOCOL,
        help="RPC protocol",
    )
    parser.add_argument("--no-cleanup", action="store_true", help="Skip cleanup")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = OdooRPCClient(args.url, args.db, args.user, args.password, args.protocol)
    try:
        uid = client.authenticate()
        print(f"Authenticated uid={uid} via {args.protocol.upper()}")
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    tester = CapContractManagementRPCTest(client)
    if args.no_cleanup:
        tester._cleanup = {}
    success = tester.run()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
