#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone RPC test for ksc_auto_invoice (Odoo 19).

No odoo-bin / shell required. Run with plain Python 3:

    python3 models/test_ksc_auto_invoice_rpc.py
    python3 models/test_ksc_auto_invoice_rpc.py --protocol xmlrpc
    python3 models/test_ksc_auto_invoice_rpc.py --url http://localhost:8069 --db odoo --user admin --password admin

Tests custom fields and business logic via public RPC APIs using exact model/field/method
names from:
  - models/sale_order.py
  - models/account_move.py
  - models/res_partner.py
  - models/res_company.py
  - models/project.py
  - models/account_analytic.py
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

MODULE_NAME = "ksc_auto_invoice"

# Odoo x2many command tuples (same as odoo.fields.Command)
CMD_CREATE = 0
CMD_UPDATE = 1
CMD_DELETE = 2
CMD_UNLINK = 2
CMD_LINK = 4
CMD_CLEAR = 5
CMD_SET = 6

# ---------------------------------------------------------------------------
# Technical names from models/sale_order.py
# ---------------------------------------------------------------------------
MODEL_SALE_ORDER = "sale.order"
MODEL_SALE_ORDER_LINE = "sale.order.line"
FIELD_SO_AUTO_INVOICE = "automatically_invoice"
FIELD_SO_DAY_OF_MONTHS = "day_of_months"
FIELD_SO_INVOICE_ACTION = "invoice_action"
FIELD_SO_MIN_AMOUNT = "minimum_amount_invoice"
FIELD_SO_NOTE = "note"
METHOD_SO_TIMESHEET_AUTO = "timesheet_invoice_auto_create"
METHOD_SO_GENERATE_DEPOSIT = "generate_deposit_invoice"
METHOD_SO_SEARCH_TIMESHEET = "search_timesheet"

# ---------------------------------------------------------------------------
# Technical names from models/account_move.py
# ---------------------------------------------------------------------------
MODEL_ACCOUNT_MOVE = "account.move"
MODEL_ACCOUNT_MOVE_LINE = "account.move.line"
FIELD_MOVE_TOTAL_MARGIN = "total_margin"
FIELD_MOVE_RISS_TIMESHEETS = "timesheet_ress_group_ids"
FIELD_MOVE_RISS_DURATION = "timesheet_riss_total_duration"
FIELD_LINE_COST = "cost"
METHOD_MOVE_RISS_ACTION = "get_riss_group_timesheet"

# ---------------------------------------------------------------------------
# Technical names from models/res_partner.py
# ---------------------------------------------------------------------------
MODEL_RES_PARTNER = "res.partner"
FIELD_PARTNER_TOTAL_DEPOSIT = "total_security_deposit"
FIELD_PARTNER_DISABLE_DEPOSIT = "desactivate_security_deposit"
METHOD_PARTNER_FETCH_DEPOSIT = "fetch_partner_paid_deposit"
METHOD_PARTNER_SECURITY_MOVES = "get_security_move_ids"

# ---------------------------------------------------------------------------
# Technical names from models/res_company.py
# ---------------------------------------------------------------------------
MODEL_RES_COMPANY = "res.company"
FIELD_COMPANY_DEPOSIT_ACCOUNT = "security_deposit_account_id"

# ---------------------------------------------------------------------------
# Technical names from models/project.py
# ---------------------------------------------------------------------------
MODEL_PROJECT = "project.project"
FIELD_PROJECT_RISS = "invoice_for_groupe_riss"
METHOD_PROJECT_RISS_CRON = "generate_invoice_rss_group"
METHOD_PROJECT_CREATE_RISS = "create_rss_invoice"

# ---------------------------------------------------------------------------
# Technical names from models/account_analytic.py
# ---------------------------------------------------------------------------
MODEL_ANALYTIC_LINE = "account.analytic.line"
FIELD_ANALYTIC_RISS_INVOICE = "riss_invoice_id"


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

    def read(self, model: str, ids: list[int], fields: list[str], context: dict | None = None) -> list[dict]:
        kwargs = {"context": context} if context else {}
        return self.execute_kw(model, "read", [ids, fields], kwargs)

    def create(self, model: str, vals: dict, context: dict | None = None) -> int:
        kwargs = {"context": context} if context else {}
        return self.execute_kw(model, "create", [vals], kwargs)

    def write(self, model: str, ids: list[int], vals: dict, context: dict | None = None) -> bool:
        kwargs = {"context": context} if context else {}
        return self.execute_kw(model, "write", [ids, vals], kwargs)

    def unlink(self, model: str, ids: list[int]) -> bool:
        return self.execute_kw(model, "unlink", [ids])

    def call(self, model: str, method: str, ids: list[int], *args, context: dict | None = None) -> Any:
        call_args = [ids] + list(args)
        kwargs = {"context": context} if context else {}
        return self.execute_kw(model, method, call_args, kwargs)

    def fields_get(self, model: str, fields: list[str] | None = None) -> dict:
        return self.execute_kw(model, "fields_get", [fields or []], {})


class KscAutoInvoiceRPCTest:
    """End-to-end ksc_auto_invoice workflow test via RPC."""

    def __init__(self, client: OdooRPCClient):
        self.client = client
        self.passed = 0
        self.failed = 0
        self._cleanup_ids: dict[str, list[int]] = {
            MODEL_SALE_ORDER: [],
            MODEL_ACCOUNT_MOVE: [],
            MODEL_RES_PARTNER: [],
            MODEL_PROJECT: [],
            MODEL_ANALYTIC_LINE: [],
            "product.product": [],
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
            return self._ok(label, True, str(exc)[:160])
        return self._ok(label, False, "expected ValidationError/UserError but RPC call succeeded")

    def _module_installed(self) -> bool:
        module_ids = self.client.search("ir.module.module", [("name", "=", MODULE_NAME), ("state", "=", "installed")])
        return bool(module_ids)

    def _get_company(self) -> dict:
        company_id = self.client.search(MODEL_RES_COMPANY, [], limit=1, order="id")[0]
        return self.client.read(MODEL_RES_COMPANY, [company_id], ["id", "name"])[0]

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

    def _get_liability_account(self, company_id: int) -> int:
        account_ids = self.client.search(
            "account.account",
            [
                ("company_ids", "in", [company_id]),
                ("account_type", "in", ["liability_current", "liability_non_current"]),
            ],
            limit=1,
            order="id",
        )
        if account_ids:
            return account_ids[0]
        return self.client.create(
            "account.account",
            {
                "name": "KSC RPC Security Deposit",
                "code": f"KSCSD{company_id}",
                "account_type": "liability_current",
                "company_ids": [(CMD_SET, 0, [company_id])],
            },
            context=self._ctx(company_id),
        )

    def _get_or_create_customer(self, suffix: str) -> int:
        name = f"KSC Auto Invoice RPC Customer {suffix}"
        existing = self.client.search(MODEL_RES_PARTNER, [("name", "=", name)], limit=1)
        if existing:
            return existing[0]
        partner_id = self.client.create(
            MODEL_RES_PARTNER,
            {"name": name, "customer_rank": 1},
        )
        self._track(MODEL_RES_PARTNER, partner_id)
        return partner_id

    def _get_or_create_product(self, name: str, list_price: float = 600.0) -> int:
        existing = self.client.search("product.product", [("name", "=", name)], limit=1)
        if existing:
            return existing[0]
        product_id = self.client.create(
            "product.product",
            {
                "name": name,
                "type": "service",
                "sale_ok": True,
                "list_price": list_price,
                "standard_price": 100.0,
            },
        )
        self._track("product.product", product_id)
        return product_id

    def _create_customer_invoice(
        self,
        partner_id: int,
        company_id: int,
        product_id: int,
        quantity: float = 1.0,
        price_unit: float = 600.0,
        cost: float = 100.0,
    ) -> int:
        move_id = self.client.create(
            MODEL_ACCOUNT_MOVE,
            {
                "move_type": "out_invoice",
                "partner_id": partner_id,
                "invoice_date": str(date.today()),
                "invoice_line_ids": [
                    (CMD_CREATE, 0, {
                        "product_id": product_id,
                        "name": "KSC RPC invoice line",
                        "quantity": quantity,
                        "price_unit": price_unit,
                        "cost": cost,
                        "tax_ids": [(CMD_CLEAR, 0, 0)],
                    })
                ],
            },
            context=self._ctx(company_id),
        )
        self._track(MODEL_ACCOUNT_MOVE, move_id)
        return move_id

    def _create_sale_order(
        self,
        partner_id: int,
        company_id: int,
        product_id: int,
        price_unit: float = 600.0,
        extra_fields: dict | None = None,
    ) -> int:
        vals = {
            "partner_id": partner_id,
            "order_line": [
                (CMD_CREATE, 0, {
                    "product_id": product_id,
                    "product_uom_qty": 1.0,
                    "price_unit": price_unit,
                })
            ],
            FIELD_SO_AUTO_INVOICE: "not_activate",
            FIELD_SO_INVOICE_ACTION: "draft",
            FIELD_SO_MIN_AMOUNT: 200.0,
        }
        if extra_fields:
            vals.update(extra_fields)
        order_id = self.client.create(MODEL_SALE_ORDER, vals, context=self._ctx(company_id))
        self._track(MODEL_SALE_ORDER, order_id)
        return order_id

    def _invoice_has_security_deposit_line(self, move_id: int) -> bool:
        line_ids = self.client.search(
            MODEL_ACCOUNT_MOVE_LINE,
            [("move_id", "=", move_id)],
        )
        if not line_ids:
            return False
        lines = self.client.read(MODEL_ACCOUNT_MOVE_LINE, line_ids, ["name"])
        return any("security deposit" in (line.get("name") or "").lower() for line in lines)

    def _cleanup(self) -> None:
        for model, ids in self._cleanup_ids.items():
            if not ids:
                continue
            try:
                if model == MODEL_ACCOUNT_MOVE:
                    for move_id in ids:
                        state = self.client.read(MODEL_ACCOUNT_MOVE, [move_id], ["state"])[0]["state"]
                        if state == "posted":
                            try:
                                self.client.call(MODEL_ACCOUNT_MOVE, "button_draft", [move_id])
                            except RuntimeError:
                                pass
                    self.client.unlink(model, ids)
                elif model == MODEL_SALE_ORDER:
                    for order_id in ids:
                        state = self.client.read(MODEL_SALE_ORDER, [order_id], ["state"])[0]["state"]
                        if state not in ("draft", "cancel"):
                            try:
                                self.client.call(MODEL_SALE_ORDER, "action_cancel", [order_id])
                            except RuntimeError:
                                pass
                    draft_ids = [
                        oid for oid in ids
                        if self.client.read(MODEL_SALE_ORDER, [oid], ["state"])[0]["state"] in ("draft", "cancel")
                    ]
                    if draft_ids:
                        self.client.unlink(MODEL_SALE_ORDER, draft_ids)
                else:
                    self.client.unlink(model, ids)
            except RuntimeError as exc:
                print(f"[WARN] cleanup {model} {ids}: {exc}")

    def _test_module_and_fields(self, company_id: int) -> None:
        """Verify module is installed and all custom fields are exposed."""
        self._ok(f"{MODULE_NAME} module installed", self._module_installed())

        field_checks = {
            MODEL_SALE_ORDER: [
                FIELD_SO_AUTO_INVOICE,
                FIELD_SO_DAY_OF_MONTHS,
                FIELD_SO_INVOICE_ACTION,
                FIELD_SO_MIN_AMOUNT,
                FIELD_SO_NOTE,
            ],
            MODEL_SALE_ORDER_LINE: ["purchase_price"],
            MODEL_ACCOUNT_MOVE: [
                FIELD_MOVE_TOTAL_MARGIN,
                FIELD_MOVE_RISS_TIMESHEETS,
                FIELD_MOVE_RISS_DURATION,
            ],
            MODEL_ACCOUNT_MOVE_LINE: [FIELD_LINE_COST],
            MODEL_RES_PARTNER: [FIELD_PARTNER_TOTAL_DEPOSIT, FIELD_PARTNER_DISABLE_DEPOSIT],
            MODEL_RES_COMPANY: [FIELD_COMPANY_DEPOSIT_ACCOUNT],
            MODEL_PROJECT: [FIELD_PROJECT_RISS],
            MODEL_ANALYTIC_LINE: [FIELD_ANALYTIC_RISS_INVOICE],
        }
        for model, fields in field_checks.items():
            model_fields = self.client.fields_get(model, fields)
            for field_name in fields:
                self._ok(f"{model}.{field_name} field exists", field_name in model_fields)

    def run(self) -> bool:
        print("=" * 80)
        print("KSC Auto Invoice — RPC test (Odoo 19)")
        print(f"Module: {MODULE_NAME}")
        print(f"Protocol: {self.client.protocol.upper()} | DB: {self.client.db} | URL: {self.client.url}")
        print("=" * 80)

        company = self._get_company()
        company_id = company["id"]
        self._ensure_chart(company_id)
        print(f"Company: {company['name']} (id={company_id})")

        self._test_module_and_fields(company_id)

        # ------------------------------------------------------------------
        # res.company — security_deposit_account_id
        # ------------------------------------------------------------------
        deposit_account_id = self._get_liability_account(company_id)
        self.client.write(
            MODEL_RES_COMPANY,
            [company_id],
            {FIELD_COMPANY_DEPOSIT_ACCOUNT: deposit_account_id},
            context=self._ctx(company_id),
        )
        company_data = self.client.read(
            MODEL_RES_COMPANY,
            [company_id],
            [FIELD_COMPANY_DEPOSIT_ACCOUNT],
        )[0]
        self._ok(
            f"{MODEL_RES_COMPANY}.{FIELD_COMPANY_DEPOSIT_ACCOUNT} writable",
            self._m2o_id(company_data[FIELD_COMPANY_DEPOSIT_ACCOUNT]) == deposit_account_id,
            str(deposit_account_id),
        )

        # ------------------------------------------------------------------
        # res.partner — security deposit fields & methods
        # ------------------------------------------------------------------
        partner_id = self._get_or_create_customer("Deposit")
        self.client.write(
            MODEL_RES_PARTNER,
            [partner_id],
            {FIELD_PARTNER_DISABLE_DEPOSIT: False},
        )
        partner_data = self.client.read(
            MODEL_RES_PARTNER,
            [partner_id],
            [FIELD_PARTNER_DISABLE_DEPOSIT, FIELD_PARTNER_TOTAL_DEPOSIT],
            context=self._ctx(company_id),
        )[0]
        self._ok(
            f"{MODEL_RES_PARTNER}.{FIELD_PARTNER_DISABLE_DEPOSIT} readable",
            partner_data[FIELD_PARTNER_DISABLE_DEPOSIT] is False,
        )
        self._ok(
            f"{MODEL_RES_PARTNER}.{FIELD_PARTNER_TOTAL_DEPOSIT} computed",
            isinstance(partner_data[FIELD_PARTNER_TOTAL_DEPOSIT], (int, float)),
            str(partner_data[FIELD_PARTNER_TOTAL_DEPOSIT]),
        )

        deposit_amount = self.client.call(
            MODEL_RES_PARTNER,
            METHOD_PARTNER_FETCH_DEPOSIT,
            [partner_id],
            deposit_account_id,
            ["not_paid", "paid"],
            context=self._ctx(company_id),
        )
        self._ok(
            f"{MODEL_RES_PARTNER}.{METHOD_PARTNER_FETCH_DEPOSIT} callable",
            isinstance(deposit_amount, (int, float)),
            str(deposit_amount),
        )

        security_moves = self.client.call(
            MODEL_RES_PARTNER,
            METHOD_PARTNER_SECURITY_MOVES,
            [partner_id],
            deposit_account_id,
            False,
            ["paid", "not_paid"],
            context=self._ctx(company_id),
        )
        self._ok(
            f"{MODEL_RES_PARTNER}.{METHOD_PARTNER_SECURITY_MOVES} callable",
            isinstance(security_moves, list),
            f"count={len(security_moves)}",
        )

        # ------------------------------------------------------------------
        # sale.order — custom fields & constraints (models/sale_order.py)
        # ------------------------------------------------------------------
        product_id = self._get_or_create_product("KSC RPC Auto Invoice Product", list_price=600.0)
        order_id = self._create_sale_order(
            partner_id,
            company_id,
            product_id,
            extra_fields={
                FIELD_SO_AUTO_INVOICE: "activated_last_day_months",
                FIELD_SO_INVOICE_ACTION: "confirmed",
                FIELD_SO_DAY_OF_MONTHS: 15,
                FIELD_SO_MIN_AMOUNT: 250.0,
            },
        )
        order_data = self.client.read(
            MODEL_SALE_ORDER,
            [order_id],
            [
                FIELD_SO_AUTO_INVOICE,
                FIELD_SO_DAY_OF_MONTHS,
                FIELD_SO_INVOICE_ACTION,
                FIELD_SO_MIN_AMOUNT,
            ],
        )[0]
        self._ok(
            f"{MODEL_SALE_ORDER} custom fields persisted",
            order_data[FIELD_SO_AUTO_INVOICE] == "activated_last_day_months"
            and order_data[FIELD_SO_DAY_OF_MONTHS] == 15
            and order_data[FIELD_SO_INVOICE_ACTION] == "confirmed"
            and order_data[FIELD_SO_MIN_AMOUNT] == 250.0,
            str(order_data),
        )

        self._expect_rpc_error(
            f"{MODEL_SALE_ORDER} constraint invalid {FIELD_SO_DAY_OF_MONTHS}",
            lambda: self.client.write(
                MODEL_SALE_ORDER,
                [order_id],
                {FIELD_SO_AUTO_INVOICE: "activated_specific_day", FIELD_SO_DAY_OF_MONTHS: 32},
            ),
        )
        self._expect_rpc_error(
            f"{MODEL_SALE_ORDER} constraint negative {FIELD_SO_MIN_AMOUNT}",
            lambda: self.client.write(MODEL_SALE_ORDER, [order_id], {FIELD_SO_MIN_AMOUNT: -10.0}),
        )

        # ------------------------------------------------------------------
        # sale.order — cron entry point exists
        # ------------------------------------------------------------------
        try:
            self.client.call(
                MODEL_SALE_ORDER,
                METHOD_SO_TIMESHEET_AUTO,
                [],
                context=self._ctx(company_id),
            )
            self._ok(f"{MODEL_SALE_ORDER}.{METHOD_SO_TIMESHEET_AUTO} callable", True)
        except RuntimeError as exc:
            self._ok(f"{MODEL_SALE_ORDER}.{METHOD_SO_TIMESHEET_AUTO} callable", False, str(exc)[:120])

        # ------------------------------------------------------------------
        # account.move — margin & RISS helpers (models/account_move.py)
        # ------------------------------------------------------------------
        invoice_id = self._create_customer_invoice(
            partner_id, company_id, product_id, quantity=2.0, price_unit=300.0, cost=50.0,
        )
        invoice_data = self.client.read(
            MODEL_ACCOUNT_MOVE,
            [invoice_id],
            [FIELD_MOVE_TOTAL_MARGIN, FIELD_MOVE_RISS_DURATION],
        )[0]
        expected_margin = (300.0 * 2.0) - (50.0 * 2.0)
        self._ok(
            f"{MODEL_ACCOUNT_MOVE}.{FIELD_MOVE_TOTAL_MARGIN} computed",
            abs(invoice_data[FIELD_MOVE_TOTAL_MARGIN] - expected_margin) < 0.01,
            f"got={invoice_data[FIELD_MOVE_TOTAL_MARGIN]} expected={expected_margin}",
        )
        self._ok(
            f"{MODEL_ACCOUNT_MOVE}.{FIELD_MOVE_RISS_DURATION} computed",
            isinstance(invoice_data[FIELD_MOVE_RISS_DURATION], (int, float)),
            str(invoice_data[FIELD_MOVE_RISS_DURATION]),
        )

        riss_action = self.client.call(MODEL_ACCOUNT_MOVE, METHOD_MOVE_RISS_ACTION, [invoice_id])
        self._ok(
            f"{MODEL_ACCOUNT_MOVE}.{METHOD_MOVE_RISS_ACTION} returns act_window",
            isinstance(riss_action, dict)
            and riss_action.get("type") == "ir.actions.act_window"
            and riss_action.get("res_model") == MODEL_ANALYTIC_LINE,
            str(riss_action.get("type")),
        )

        line_ids = self.client.search(
            MODEL_ACCOUNT_MOVE_LINE,
            [("move_id", "=", invoice_id), ("display_type", "=", "product")],
            limit=1,
        )
        if line_ids:
            line_data = self.client.read(MODEL_ACCOUNT_MOVE_LINE, line_ids, [FIELD_LINE_COST])[0]
            self._ok(
                f"{MODEL_ACCOUNT_MOVE_LINE}.{FIELD_LINE_COST} on invoice line",
                line_data[FIELD_LINE_COST] == 50.0,
                str(line_data[FIELD_LINE_COST]),
            )

        # ------------------------------------------------------------------
        # Security deposit line via generate_deposit_invoice (models/sale_order.py)
        # ------------------------------------------------------------------
        try:
            self.client.call(
                MODEL_SALE_ORDER,
                METHOD_SO_GENERATE_DEPOSIT,
                [order_id],
                invoice_id,
                context=self._ctx(company_id),
            )
            self._ok(
                f"{MODEL_SALE_ORDER}.{METHOD_SO_GENERATE_DEPOSIT} adds deposit line",
                self._invoice_has_security_deposit_line(invoice_id),
                f"invoice_id={invoice_id}",
            )
        except RuntimeError as exc:
            self._ok(
                f"{MODEL_SALE_ORDER}.{METHOD_SO_GENERATE_DEPOSIT} adds deposit line",
                False,
                str(exc)[:120],
            )

        # ------------------------------------------------------------------
        # project.project — invoice_for_groupe_riss (models/project.py)
        # ------------------------------------------------------------------
        project_ids = self.client.search(MODEL_PROJECT, [], limit=1, order="id")
        if project_ids:
            project_id = project_ids[0]
            self.client.write(
                MODEL_PROJECT,
                [project_id],
                {FIELD_PROJECT_RISS: True},
                context=self._ctx(company_id),
            )
            project_data = self.client.read(MODEL_PROJECT, [project_id], [FIELD_PROJECT_RISS])[0]
            self._ok(
                f"{MODEL_PROJECT}.{FIELD_PROJECT_RISS} writable",
                project_data[FIELD_PROJECT_RISS] is True,
            )
            try:
                self.client.call(
                    MODEL_PROJECT,
                    METHOD_PROJECT_RISS_CRON,
                    [],
                    context=self._ctx(company_id),
                )
                self._ok(f"{MODEL_PROJECT}.{METHOD_PROJECT_RISS_CRON} callable", True)
            except RuntimeError as exc:
                self._ok(f"{MODEL_PROJECT}.{METHOD_PROJECT_RISS_CRON} callable", False, str(exc)[:120])
        else:
            self._ok(f"{MODEL_PROJECT} record available for {FIELD_PROJECT_RISS} test", False, "no project found")

        # ------------------------------------------------------------------
        # account.analytic.line — riss_invoice_id write guard (models/account_analytic.py)
        # ------------------------------------------------------------------
        employee_ids = self.client.search("hr.employee", [], limit=1)
        project_id_for_ts = project_ids[0] if project_ids else None
        if employee_ids and project_id_for_ts:
            timesheet_id = self.client.create(
                MODEL_ANALYTIC_LINE,
                {
                    "name": "KSC RPC timesheet",
                    "date": str(date.today()),
                    "unit_amount": 1.0,
                    "employee_id": employee_ids[0],
                    "project_id": project_id_for_ts,
                },
                context=self._ctx(company_id),
            )
            self._track(MODEL_ANALYTIC_LINE, timesheet_id)
            self.client.write(
                MODEL_ANALYTIC_LINE,
                [timesheet_id],
                {FIELD_ANALYTIC_RISS_INVOICE: invoice_id},
                context=self._ctx(company_id),
            )
            ts_data = self.client.read(MODEL_ANALYTIC_LINE, [timesheet_id], [FIELD_ANALYTIC_RISS_INVOICE])[0]
            self._ok(
                f"{MODEL_ANALYTIC_LINE}.{FIELD_ANALYTIC_RISS_INVOICE} linkable on draft invoice",
                self._m2o_id(ts_data[FIELD_ANALYTIC_RISS_INVOICE]) == invoice_id,
            )
            self._expect_rpc_error(
                f"{MODEL_ANALYTIC_LINE} blocks unit_amount write when linked to invoice",
                lambda: self.client.write(
                    MODEL_ANALYTIC_LINE,
                    [timesheet_id],
                    {"unit_amount": 2.0},
                    context=self._ctx(company_id),
                ),
            )
        else:
            self._ok(
                f"{MODEL_ANALYTIC_LINE} invoiced write-guard test",
                False,
                "skipped (need hr.employee and project.project)",
            )

        print("=" * 80)
        print(f"Result: {self.passed} passed, {self.failed} failed")
        print("=" * 80)

        self._cleanup()
        return self.failed == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RPC test for ksc_auto_invoice (Odoo 19)",
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

    success = KscAutoInvoiceRPCTest(client).run()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
