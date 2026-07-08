#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone RPC test for ksc_product_and_account_restriction_by_partner (Odoo 19).

No odoo-bin / shell required. Run with plain Python 3:

    python3 models/test_product_account_restriction_rpc.py
    python3 models/test_product_account_restriction_rpc.py --protocol xmlrpc
    python3 models/test_product_account_restriction_rpc.py --url http://localhost:8069 --db odoo --user admin --password admin

Tests product/account restriction on vendor bills via public RPC APIs using exact
model/field/method names from:
  - models/product_account_restriction.py  (product.account.restriction)
  - models/account_move.py                 (account.move.line inheritance)
"""
from __future__ import annotations

import argparse
import sys
import xmlrpc.client
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json


# ---------------------------------------------------------------------------
# Configuration (override via CLI args)
# ---------------------------------------------------------------------------
DEFAULT_URL = "http://localhost:8069"
DEFAULT_DB = "odoo"
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "admin"
DEFAULT_PROTOCOL = "jsonrpc"  # jsonrpc | xmlrpc

MODULE_NAME = "ksc_product_and_account_restriction_by_partner"

# Odoo x2many command tuples (same as odoo.fields.Command)
CMD_CREATE = 0
CMD_UPDATE = 1
CMD_DELETE = 2
CMD_UNLINK = 2
CMD_LINK = 4
CMD_CLEAR = 5
CMD_SET = 6

# Technical names from models/product_account_restriction.py
MODEL_PRODUCT_ACCOUNT_RESTRICTION = "product.account.restriction"
FIELD_RESTRICTION_NAME = "name"
FIELD_RESTRICTION_PARTNER = "partner_id"
FIELD_RESTRICTION_COMPANY = "company_id"
FIELD_RESTRICTION_ALLOWED_PRODUCTS = "allowed_product_ids"
FIELD_RESTRICTION_ALLOWED_ACCOUNTS = "allowed_account_ids"
METHOD_RESTRICTION_CHECK_UNIQUE = "_check_model_name"

# Technical names from models/account_move.py (account.move.line inherit)
MODEL_ACCOUNT_MOVE = "account.move"
MODEL_ACCOUNT_MOVE_LINE = "account.move.line"
METHOD_LINE_CREATE = "create"
METHOD_LINE_WRITE = "write"
METHOD_LINE_CHECK_RESTRICTION = "_check_product_account_restriction"
MOVE_TYPE_VENDOR_BILL = "in_invoice"
MOVE_TYPE_CUSTOMER_INVOICE = "out_invoice"


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
            self._xml_common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common", allow_none=True)
            self._xml_models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object", allow_none=True)
            uid = self._xml_common.authenticate(self.db, self.username, self.password, {})
            if not uid:
                raise RuntimeError("Authentication failed. Check URL, database, username, and password.")
            self.uid = uid
            return uid

        uid = self._jsonrpc("common", "authenticate", [self.db, self.username, self.password, {}])
        if not uid:
            raise RuntimeError("Authentication failed. Check URL, database, username, and password.")
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

    def execute_kw(self, model: str, method: str, args: list | None = None, kwargs: dict | None = None) -> Any:
        if self.uid is None:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        args = args or []
        kwargs = kwargs or {}
        if self.protocol == "xmlrpc":
            return self._xml_models.execute_kw(self.db, self.uid, self.password, model, method, args, kwargs)
        return self._jsonrpc("object", "execute_kw", [self.db, self.uid, self.password, model, method, args, kwargs])

    def search(self, model: str, domain: list, limit: int | None = None, order: str | None = None) -> list[int]:
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

    def write(self, model: str, ids: list[int], vals: dict, context: dict | None = None) -> bool:
        kwargs = {"context": context} if context else {}
        return self.execute_kw(model, "write", [ids, vals], kwargs)

    def unlink(self, model: str, ids: list[int]) -> bool:
        return self.execute_kw(model, "unlink", [ids])

    def call(self, model: str, method: str, ids: list[int], context: dict | None = None) -> Any:
        kwargs = {"context": context} if context else {}
        return self.execute_kw(model, method, [ids], kwargs)

    def fields_get(self, model: str, fields: list[str] | None = None) -> dict:
        return self.execute_kw(model, "fields_get", [fields or []], {})


class ProductAccountRestrictionRPCTest:
    """End-to-end product/account restriction workflow test via RPC."""

    def __init__(self, client: OdooRPCClient):
        self.client = client
        self.passed = 0
        self.failed = 0
        self._cleanup_ids: dict[str, list[int]] = {
            MODEL_PRODUCT_ACCOUNT_RESTRICTION: [],
            MODEL_ACCOUNT_MOVE: [],
            "res.partner": [],
            "product.product": [],
            "account.account": [],
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
            return self._ok(label, True, str(exc)[:120])
        return self._ok(label, False, "expected ValidationError but RPC call succeeded")

    def _get_company(self) -> dict:
        company_id = self.client.search("res.company", [], limit=1, order="id")[0]
        return self.client.read("res.company", [company_id], ["id", "name"])[0]

    def _ensure_chart(self, company_id: int) -> None:
        account_ids = self.client.search(
            "account.account",
            [("company_ids", "in", [company_id])],
            limit=1,
        )
        if not account_ids:
            self.client.execute_kw(
                "account.chart.template",
                "try_loading",
                ["generic_coa", company_id],
                {"install_demo": False},
            )

    def _get_or_create_vendor(self, suffix: str) -> int:
        name = f"KSC RPC Vendor {suffix}"
        existing = self.client.search("res.partner", [("name", "=", name)], limit=1)
        if existing:
            return existing[0]
        partner_id = self.client.create(
            "res.partner",
            {"name": name, "supplier_rank": 1},
        )
        self._track("res.partner", partner_id)
        return partner_id

    def _get_or_create_product(self, name: str) -> int:
        existing = self.client.search("product.product", [("name", "=", name)], limit=1)
        if existing:
            return existing[0]
        product_id = self.client.create(
            "product.product",
            {
                "name": name,
                "type": "service",
                "purchase_ok": True,
                "standard_price": 50.0,
            },
        )
        self._track("product.product", product_id)
        return product_id

    def _get_expense_accounts(self, company_id: int, count: int = 2) -> list[int]:
        account_ids = self.client.search(
            "account.account",
            [
                ("company_ids", "in", [company_id]),
                ("account_type", "in", ["expense", "expense_direct_cost", "expense_depreciation"]),
            ],
            limit=count,
            order="id",
        )
        if len(account_ids) >= count:
            return account_ids

        created = []
        for idx in range(count - len(account_ids)):
            account_id = self.client.create(
                "account.account",
                {
                    "name": f"KSC RPC Expense Account {idx + 1}",
                    "code": f"KSC{company_id}{idx + 1:03d}",
                    "account_type": "expense",
                    "company_ids": [(CMD_SET, 0, [company_id])],
                },
                context=self._ctx(company_id),
            )
            self._track("account.account", account_id)
            created.append(account_id)
        return account_ids + created

    def _create_restriction(
        self,
        partner_id: int,
        company_id: int,
        allowed_product_ids: list[int] | None = None,
        allowed_account_ids: list[int] | None = None,
    ) -> int:
        vals = {
            FIELD_RESTRICTION_PARTNER: partner_id,
            FIELD_RESTRICTION_COMPANY: company_id,
        }
        if allowed_product_ids is not None:
            vals[FIELD_RESTRICTION_ALLOWED_PRODUCTS] = [(CMD_SET, 0, allowed_product_ids)]
        if allowed_account_ids is not None:
            vals[FIELD_RESTRICTION_ALLOWED_ACCOUNTS] = [(CMD_SET, 0, allowed_account_ids)]

        restriction_id = self.client.create(
            MODEL_PRODUCT_ACCOUNT_RESTRICTION,
            vals,
            context=self._ctx(company_id),
        )
        self._track(MODEL_PRODUCT_ACCOUNT_RESTRICTION, restriction_id)
        return restriction_id

    def _create_vendor_bill(
        self,
        partner_id: int,
        company_id: int,
        product_id: int | None = None,
        account_id: int | None = None,
        quantity: float = 1.0,
        price_unit: float = 100.0,
    ) -> int:
        today = str(date.today())
        line_vals: dict[str, Any] = {
            "name": "KSC RPC vendor bill line",
            "quantity": quantity,
            "price_unit": price_unit,
            "tax_ids": [(CMD_CLEAR, 0, 0)],
        }
        if product_id:
            line_vals["product_id"] = product_id
        if account_id:
            line_vals["account_id"] = account_id

        move_id = self.client.create(
            MODEL_ACCOUNT_MOVE,
            {
                "move_type": MOVE_TYPE_VENDOR_BILL,
                "partner_id": partner_id,
                "invoice_date": today,
                "invoice_line_ids": [(CMD_CREATE, 0, line_vals)],
            },
            context=self._ctx(company_id),
        )
        self._track(MODEL_ACCOUNT_MOVE, move_id)
        return move_id

    def _write_vendor_bill_line(
        self,
        move_id: int,
        company_id: int,
        product_id: int | None = None,
        account_id: int | None = None,
    ) -> None:
        line_ids = self.client.search(
            MODEL_ACCOUNT_MOVE_LINE,
            [
                ("move_id", "=", move_id),
                ("display_type", "=", "product"),
            ],
            limit=1,
        )
        if not line_ids:
            line_ids = self.client.search(
                MODEL_ACCOUNT_MOVE_LINE,
                [("move_id", "=", move_id), ("product_id", "!=", False)],
                limit=1,
            )
        vals: dict[str, Any] = {}
        if product_id is not None:
            vals["product_id"] = product_id
        if account_id is not None:
            vals["account_id"] = account_id
        self.client.write(MODEL_ACCOUNT_MOVE_LINE, line_ids, vals, context=self._ctx(company_id))

    def _cleanup(self) -> None:
        for model, ids in self._cleanup_ids.items():
            if not ids:
                continue
            try:
                posted_moves = []
                draft_moves = []
                for move_id in ids:
                    if model != MODEL_ACCOUNT_MOVE:
                        break
                    state = self.client.read(MODEL_ACCOUNT_MOVE, [move_id], ["state"])[0]["state"]
                    (posted_moves if state == "posted" else draft_moves).append(move_id)
                if model == MODEL_ACCOUNT_MOVE:
                    for move_id in posted_moves:
                        try:
                            self.client.call(MODEL_ACCOUNT_MOVE, "button_draft", [move_id])
                        except RuntimeError:
                            pass
                    self.client.unlink(model, ids)
                else:
                    self.client.unlink(model, ids)
            except RuntimeError as exc:
                print(f"[WARN] cleanup {model} {ids}: {exc}")

    def run(self) -> bool:
        print("=" * 80)
        print("KSC Product & Account Restriction By Partner — RPC test (Odoo 19)")
        print(f"Module: {MODULE_NAME}")
        print(f"Protocol: {self.client.protocol.upper()} | DB: {self.client.db} | URL: {self.client.url}")
        print("=" * 80)

        company = self._get_company()
        company_id = company["id"]
        self._ensure_chart(company_id)
        print(f"Company: {company['name']} (id={company_id})")

        # ------------------------------------------------------------------
        # 1) product.account.restriction — model & fields exist
        # ------------------------------------------------------------------
        restriction_fields = self.client.fields_get(
            MODEL_PRODUCT_ACCOUNT_RESTRICTION,
            [
                FIELD_RESTRICTION_NAME,
                FIELD_RESTRICTION_PARTNER,
                FIELD_RESTRICTION_COMPANY,
                FIELD_RESTRICTION_ALLOWED_PRODUCTS,
                FIELD_RESTRICTION_ALLOWED_ACCOUNTS,
            ],
        )
        for field_name in (
            FIELD_RESTRICTION_NAME,
            FIELD_RESTRICTION_PARTNER,
            FIELD_RESTRICTION_COMPANY,
            FIELD_RESTRICTION_ALLOWED_PRODUCTS,
            FIELD_RESTRICTION_ALLOWED_ACCOUNTS,
        ):
            self._ok(f"{MODEL_PRODUCT_ACCOUNT_RESTRICTION}.{field_name} field exists", field_name in restriction_fields)

        # ------------------------------------------------------------------
        # 2) Setup test data
        # ------------------------------------------------------------------
        vendor_id = self._get_or_create_vendor("Restricted")
        unrestricted_vendor_id = self._get_or_create_vendor("Unrestricted")
        allowed_product_id = self._get_or_create_product("KSC RPC Allowed Product")
        blocked_product_id = self._get_or_create_product("KSC RPC Blocked Product")
        expense_accounts = self._get_expense_accounts(company_id, count=2)
        allowed_account_id, blocked_account_id = expense_accounts[0], expense_accounts[1]

        restriction_id = self._create_restriction(
            vendor_id,
            company_id,
            allowed_product_ids=[allowed_product_id],
            allowed_account_ids=[allowed_account_id],
        )
        restriction = self.client.read(
            MODEL_PRODUCT_ACCOUNT_RESTRICTION,
            [restriction_id],
            [
                FIELD_RESTRICTION_NAME,
                FIELD_RESTRICTION_PARTNER,
                FIELD_RESTRICTION_COMPANY,
                FIELD_RESTRICTION_ALLOWED_PRODUCTS,
                FIELD_RESTRICTION_ALLOWED_ACCOUNTS,
            ],
        )[0]

        self._ok(
            f"{MODEL_PRODUCT_ACCOUNT_RESTRICTION}.{FIELD_RESTRICTION_NAME} related to partner",
            restriction[FIELD_RESTRICTION_NAME] is not False,
            str(restriction[FIELD_RESTRICTION_NAME]),
        )
        self._ok(
            f"{MODEL_PRODUCT_ACCOUNT_RESTRICTION}.{FIELD_RESTRICTION_PARTNER} set",
            self._m2o_id(restriction[FIELD_RESTRICTION_PARTNER]) == vendor_id,
        )
        self._ok(
            f"{MODEL_PRODUCT_ACCOUNT_RESTRICTION}.{FIELD_RESTRICTION_ALLOWED_PRODUCTS} contains allowed product",
            allowed_product_id in restriction[FIELD_RESTRICTION_ALLOWED_PRODUCTS],
        )
        self._ok(
            f"{MODEL_PRODUCT_ACCOUNT_RESTRICTION}.{FIELD_RESTRICTION_ALLOWED_ACCOUNTS} contains allowed account",
            allowed_account_id in restriction[FIELD_RESTRICTION_ALLOWED_ACCOUNTS],
        )

        # ------------------------------------------------------------------
        # 3) product.account.restriction._check_model_name — unique partner/company
        # ------------------------------------------------------------------
        self._expect_rpc_error(
            f"{MODEL_PRODUCT_ACCOUNT_RESTRICTION}.{METHOD_RESTRICTION_CHECK_UNIQUE} duplicate partner+company",
            lambda: self._create_restriction(
                vendor_id,
                company_id,
                allowed_product_ids=[allowed_product_id],
            ),
        )

        # ------------------------------------------------------------------
        # 4) account.move.line.create + _check_product_account_restriction
        #    Vendor bill with allowed product -> success
        # ------------------------------------------------------------------
        try:
            allowed_move_id = self._create_vendor_bill(
                vendor_id,
                company_id,
                product_id=allowed_product_id,
                account_id=allowed_account_id,
            )
            self._ok(
                f"{MODEL_ACCOUNT_MOVE_LINE}.{METHOD_LINE_CREATE} allowed product on {MOVE_TYPE_VENDOR_BILL}",
                bool(allowed_move_id),
                str(allowed_move_id),
            )
        except RuntimeError as exc:
            self._ok(
                f"{MODEL_ACCOUNT_MOVE_LINE}.{METHOD_LINE_CREATE} allowed product on {MOVE_TYPE_VENDOR_BILL}",
                False,
                str(exc),
            )
            allowed_move_id = None

        # ------------------------------------------------------------------
        # 5) Blocked product on vendor bill -> ValidationError
        # ------------------------------------------------------------------
        self._expect_rpc_error(
            f"{MODEL_ACCOUNT_MOVE_LINE}.{METHOD_LINE_CHECK_RESTRICTION} blocks disallowed product",
            lambda: self._create_vendor_bill(
                vendor_id,
                company_id,
                product_id=blocked_product_id,
                account_id=allowed_account_id,
            ),
        )

        # ------------------------------------------------------------------
        # 6) Blocked account on vendor bill -> ValidationError
        # ------------------------------------------------------------------
        self._expect_rpc_error(
            f"{MODEL_ACCOUNT_MOVE_LINE}.{METHOD_LINE_CHECK_RESTRICTION} blocks disallowed account",
            lambda: self._create_vendor_bill(
                vendor_id,
                company_id,
                product_id=allowed_product_id,
                account_id=blocked_account_id,
            ),
        )

        # ------------------------------------------------------------------
        # 7) account.move.line.write + _check_product_account_restriction
        # ------------------------------------------------------------------
        if allowed_move_id:
            self._expect_rpc_error(
                f"{MODEL_ACCOUNT_MOVE_LINE}.{METHOD_LINE_WRITE} blocks product change to disallowed",
                lambda: self._write_vendor_bill_line(
                    allowed_move_id,
                    company_id,
                    product_id=blocked_product_id,
                ),
            )

        # ------------------------------------------------------------------
        # 8) No restriction configured for partner -> any product allowed
        # ------------------------------------------------------------------
        try:
            free_move_id = self._create_vendor_bill(
                unrestricted_vendor_id,
                company_id,
                product_id=blocked_product_id,
                account_id=blocked_account_id,
            )
            self._ok(
                f"{MODEL_ACCOUNT_MOVE_LINE}.{METHOD_LINE_CHECK_RESTRICTION} skipped when no restriction",
                bool(free_move_id),
                str(free_move_id),
            )
        except RuntimeError as exc:
            self._ok(
                f"{MODEL_ACCOUNT_MOVE_LINE}.{METHOD_LINE_CHECK_RESTRICTION} skipped when no restriction",
                False,
                str(exc),
            )

        # ------------------------------------------------------------------
        # 9) Customer invoice (out_invoice) is not restricted
        # ------------------------------------------------------------------
        try:
            customer_invoice_id = self.client.create(
                MODEL_ACCOUNT_MOVE,
                {
                    "move_type": MOVE_TYPE_CUSTOMER_INVOICE,
                    "partner_id": vendor_id,
                    "invoice_line_ids": [
                        (CMD_CREATE, 0, {
                            "product_id": blocked_product_id,
                            "quantity": 1.0,
                            "price_unit": 100.0,
                            "tax_ids": [(CMD_CLEAR, 0, 0)],
                        })
                    ],
                },
                context=self._ctx(company_id),
            )
            self._track(MODEL_ACCOUNT_MOVE, customer_invoice_id)
            self._ok(
                f"{MODEL_ACCOUNT_MOVE_LINE}.{METHOD_LINE_CHECK_RESTRICTION} ignores {MOVE_TYPE_CUSTOMER_INVOICE}",
                bool(customer_invoice_id),
                str(customer_invoice_id),
            )
        except RuntimeError as exc:
            self._ok(
                f"{MODEL_ACCOUNT_MOVE_LINE}.{METHOD_LINE_CHECK_RESTRICTION} ignores {MOVE_TYPE_CUSTOMER_INVOICE}",
                False,
                str(exc),
            )

        # ------------------------------------------------------------------
        # 10) Payable line on vendor bill is skipped (no product, payable account)
        # ------------------------------------------------------------------
        partner_data = self.client.read("res.partner", [vendor_id], ["property_account_payable_id"])[0]
        payable_account_id = self._m2o_id(partner_data["property_account_payable_id"])
        if payable_account_id and allowed_move_id:
            payable_lines = self.client.search(
                MODEL_ACCOUNT_MOVE_LINE,
                [
                    ("move_id", "=", allowed_move_id),
                    ("account_id", "=", payable_account_id),
                ],
            )
            self._ok(
                f"{MODEL_ACCOUNT_MOVE_LINE}.{METHOD_LINE_CHECK_RESTRICTION} skips payable line",
                bool(payable_lines),
                f"payable_line_ids={payable_lines}",
            )

        # ------------------------------------------------------------------
        # 11) Search restriction by partner_id + company_id (as in account_move.py)
        # ------------------------------------------------------------------
        found_ids = self.client.search(
            MODEL_PRODUCT_ACCOUNT_RESTRICTION,
            [
                (FIELD_RESTRICTION_PARTNER, "=", vendor_id),
                "|",
                (FIELD_RESTRICTION_COMPANY, "=", company_id),
                (FIELD_RESTRICTION_COMPANY, "=", False),
            ],
        )
        self._ok(
            f"{MODEL_PRODUCT_ACCOUNT_RESTRICTION}.search partner+company domain",
            restriction_id in found_ids,
            str(found_ids),
        )

        print("=" * 80)
        print(f"Result: {self.passed} passed, {self.failed} failed")
        print("=" * 80)

        self._cleanup()
        return self.failed == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RPC test for ksc_product_and_account_restriction_by_partner (Odoo 19)",
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

    success = ProductAccountRestrictionRPCTest(client).run()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
