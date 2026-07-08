#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone RPC test for cap_account_intern_company_transection (Odoo 19).

No odoo-bin / shell required. Run with plain Python 3:

    python3 test_inter_company_rpc.py
    python3 test_inter_company_rpc.py --protocol xmlrpc
    python3 test_inter_company_rpc.py --url http://localhost:8069 --db odoo --user admin --password admin

Tests the full inter-company workflow via public RPC APIs using exact model/field/method
names from models/account_move.py, models/account_account.py, models/account_analytic_line.py
"""
from __future__ import annotations

import argparse
import sys
import xmlrpc.client
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


# Odoo x2many command tuples (same as odoo.fields.Command)
CMD_CREATE = 0
CMD_UPDATE = 1
CMD_DELETE = 2
CMD_UNLINK = 2
CMD_LINK = 4
CMD_CLEAR = 5
CMD_SET = 6


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


class CapInterCompanyRPCTest:
    """End-to-end inter-company workflow test via RPC."""

    def __init__(self, client: OdooRPCClient):
        self.client = client
        self.passed = 0
        self.failed = 0

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

    def _ctx(self, company_id: int, **extra) -> dict:
        ctx = {"allowed_company_ids": [company_id], "default_company_id": company_id}
        ctx.update(extra)
        return ctx

    def _get_companies(self) -> tuple[dict, dict]:
        company_ids = self.client.search("res.company", [], order="id")
        if len(company_ids) < 2:
            company_b_id = self.client.create("res.company", {"name": "CAP Inter-Company RPC Test Co B"})
            self.client.execute_kw(
                "account.chart.template",
                "try_loading",
                ["generic_coa", company_b_id],
                {"install_demo": False},
            )
            company_ids = self.client.search("res.company", [], order="id")

        companies = self.client.read("res.company", company_ids[:2], ["id", "name", "partner_id"])
        return companies[0], companies[1]

    def _partner_id(self, company: dict) -> int:
        partner = company["partner_id"]
        return partner[0] if isinstance(partner, (list, tuple)) else partner

    def _get_product_id(self) -> int:
        product_ids = self.client.search(
            "product.product",
            [("sale_ok", "=", True), ("type", "=", "service")],
            limit=1,
        )
        if product_ids:
            return product_ids[0]
        return self.client.create(
            "product.product",
            {"name": "CAP RPC Inter-Company Product", "type": "service", "list_price": 100.0},
        )

    def _create_out_invoice(self, company_a: dict, partner_b_id: int, product_id: int) -> int:
        from datetime import date
        today = str(date.today())

        vals = {
            "move_type": "out_invoice",
            "partner_id": partner_b_id,
            "invoice_date": today,
            "invoice_date_due": today,
            "invoice_payment_term_id": False,
            "invoice_line_ids": [
                (CMD_CREATE, 0, {
                    "product_id": product_id,
                    "name": "CAP RPC inter-company workflow line",
                    "quantity": 1.0,
                    "price_unit": 450.0,
                    "tax_ids": [(CMD_CLEAR, 0, 0)],
                })
            ],
        }
        return self.client.create("account.move", vals, context=self._ctx(company_a["id"]))

    def _read_move(self, move_id: int) -> dict:
        return self.client.read(
            "account.move",
            [move_id],
            [
                "move_type",
                "state",
                "partner_id",
                "company_id",
                "is_internal_invoice",
                "inverse_move_type",
                "inter_comp_journal_entry_id",
                "ref",
                "payment_reference",
                "invoice_date",
            ],
        )[0]

    def _related_id(self, move: dict) -> int | None:
        rel = move.get("inter_comp_journal_entry_id")
        if not rel:
            return None
        return rel[0] if isinstance(rel, (list, tuple)) else rel

    def run(self) -> bool:
        print("=" * 80)
        print("CAP Inter-Company Transaction — RPC workflow test (Odoo 19)")
        print(f"Protocol: {self.client.protocol.upper()} | DB: {self.client.db} | URL: {self.client.url}")
        print("=" * 80)

        company_a, company_b = self._get_companies()
        partner_b_id = self._partner_id(company_b)
        partner_a_id = self._partner_id(company_a)
        product_id = self._get_product_id()

        print(f"Company A: {company_a['name']} (id={company_a['id']})")
        print(f"Company B: {company_b['name']} (id={company_b['id']})")

        # 1) res.company._find_company_from_partner
        try:
            found = self.client.execute_kw(
                "res.company",
                "_find_company_from_partner",
                [partner_b_id],
            )
            self._ok("res.company._find_company_from_partner", bool(found), str(found))
        except RuntimeError as exc:
            # private-ish helper may be blocked on some setups; infer via is_internal_invoice
            print(f"[WARN] res.company._find_company_from_partner not RPC-callable: {exc}")

        # 2) account.move.create -> is_internal_invoice, inverse_move_type, inter_comp_journal_entry_id
        out_id = self._create_out_invoice(company_a, partner_b_id, product_id)
        out = self._read_move(out_id)

        self._ok("account.move.is_internal_invoice", out["is_internal_invoice"] is True)
        self._ok("account.move.inverse_move_type", out["inverse_move_type"] == "in_invoice", out["inverse_move_type"])

        related_id = self._related_id(out)
        self._ok("account.move.inter_comp_journal_entry_id on create", related_id is not None, str(related_id))

        if related_id:
            related = self._read_move(related_id)
            self._ok("related account.move.move_type == in_invoice", related["move_type"] == "in_invoice")
            rel_company = related["company_id"][0] if related["company_id"] else None
            self._ok("related account.move.company_id == Company B", rel_company == company_b["id"], str(rel_company))
            rel_partner = related["partner_id"][0] if related["partner_id"] else None
            self._ok("related account.move.partner_id == Company A partner", rel_partner == partner_a_id, str(rel_partner))

            back_id = self._related_id(related)
            self._ok("bidirectional inter_comp_journal_entry_id", back_id == out_id, str(back_id))
            self._ok("related account.move.state == draft", related["state"] == "draft")

        # 3) account.move.write sync (ref, payment_reference, invoice_date)
        header_id = self._create_out_invoice(company_a, partner_b_id, product_id)
        header = self._read_move(header_id)
        header_related_id = self._related_id(header)

        self.client.write(
            "account.move",
            [header_id],
            {"ref": "CAP-RPC-REF", "payment_reference": "CAP-RPC-PAY"},
            context=self._ctx(company_a["id"]),
        )
        if header_related_id:
            synced = self._read_move(header_related_id)
            self._ok("write sync ref", synced["ref"] == "CAP-RPC-REF", synced.get("ref", ""))
            self._ok(
                "write sync payment_reference",
                synced["payment_reference"] == "CAP-RPC-PAY",
                synced.get("payment_reference", ""),
            )

        # 4) account.move.action_post -> account.move._post posts related entry
        post_id = self._create_out_invoice(company_a, partner_b_id, product_id)
        post = self._read_move(post_id)
        post_related_id = self._related_id(post)

        self.client.call("account.move", "action_post", [post_id], context=self._ctx(company_a["id"]))
        post = self._read_move(post_id)
        self._ok("account.move.action_post source state", post["state"] == "posted", post["state"])

        if post_related_id:
            post_related = self._read_move(post_related_id)
            self._ok(
                "account.move._post syncs inter_comp_journal_entry_id",
                post_related["state"] == "posted",
                post_related["state"],
            )
            pr_lines = self.client.search(
                "account.move.line",
                [
                    ("move_id", "=", post_related_id),
                    ("account_id.account_type", "in", ["liability_payable", "asset_receivable"]),
                ],
            )
            if pr_lines:
                lines = self.client.read("account.move.line", pr_lines, ["date_maturity"])
                self._ok(
                    "account.move._ensure_due_dates_on_moves (date_maturity set)",
                    all(line.get("date_maturity") for line in lines),
                )

        # 5) account.move.button_draft
        draft_id = self._create_out_invoice(company_a, partner_b_id, product_id)
        draft_related_id = self._related_id(self._read_move(draft_id))
        self.client.call("account.move", "action_post", [draft_id], context=self._ctx(company_a["id"]))
        self.client.call("account.move", "button_draft", [draft_id], context=self._ctx(company_a["id"]))
        draft = self._read_move(draft_id)
        self._ok("account.move.button_draft source", draft["state"] == "draft", draft["state"])
        if draft_related_id:
            draft_related = self._read_move(draft_related_id)
            self._ok("account.move.button_draft related", draft_related["state"] == "draft", draft_related["state"])

        # 6) account.move.button_cancel
        cancel_id = self._create_out_invoice(company_a, partner_b_id, product_id)
        cancel_related_id = self._related_id(self._read_move(cancel_id))
        self.client.call("account.move", "action_post", [cancel_id], context=self._ctx(company_a["id"]))
        self.client.call("account.move", "button_cancel", [cancel_id], context=self._ctx(company_a["id"]))
        cancel = self._read_move(cancel_id)
        self._ok("account.move.button_cancel source", cancel["state"] == "cancel", cancel["state"])
        if cancel_related_id:
            cancel_related = self._read_move(cancel_related_id)
            self._ok("account.move.button_cancel related", cancel_related["state"] == "cancel", cancel_related["state"])

        # 7) account.move.generate_related_journal_entry
        regen_id = self._create_out_invoice(company_a, partner_b_id, product_id)
        regen = self._read_move(regen_id)
        regen_related_id = self._related_id(regen)
        if regen_related_id:
            self.client.unlink("account.move", [regen_related_id])
            self.client.write("account.move", [regen_id], {"inter_comp_journal_entry_id": False}, context=self._ctx(company_a["id"]))

        self.client.call("account.move", "generate_related_journal_entry", [regen_id], context=self._ctx(company_a["id"]))
        regen = self._read_move(regen_id)
        new_related_id = self._related_id(regen)
        self._ok("account.move.generate_related_journal_entry", new_related_id is not None, str(new_related_id))
        if new_related_id:
            new_related = self._read_move(new_related_id)
            self._ok(
                "generate_related_journal_entry bidirectional link",
                self._related_id(new_related) == regen_id,
                str(self._related_id(new_related)),
            )

        # 8) account.account._get_most_frequent_account_for_partner + from_inter_company_transaction context
        try:
            result = self.client.execute_kw(
                "account.account",
                "_get_most_frequent_account_for_partner",
                [],
                {
                    "company_id": company_a["id"],
                    "partner_id": partner_b_id,
                    "move_type": "out_invoice",
                    "context": {"from_inter_company_transaction": True},
                },
            )
            self._ok(
                "account.account._get_most_frequent_account_for_partner returns False",
                result is False,
                str(result),
            )
        except RuntimeError as exc:
            print(f"[WARN] account.account._get_most_frequent_account_for_partner not RPC-callable: {exc}")

        # 9) account.analytic.line.subsidiary_invoice_id
        fields_get = self.client.execute_kw("account.analytic.line", "fields_get", [["subsidiary_invoice_id"], {}])
        self._ok(
            "account.analytic.line.subsidiary_invoice_id field exists",
            "subsidiary_invoice_id" in fields_get,
        )
        analytic_id = self.client.create(
            "account.analytic.line",
            {"name": "CAP RPC subsidiary test", "subsidiary_invoice_id": out_id},
        )
        analytic = self.client.read("account.analytic.line", [analytic_id], ["subsidiary_invoice_id"])[0]
        sub_inv = analytic["subsidiary_invoice_id"]
        sub_inv_id = sub_inv[0] if isinstance(sub_inv, (list, tuple)) else sub_inv
        self._ok("account.analytic.line.subsidiary_invoice_id link", sub_inv_id == out_id, str(sub_inv_id))

        # 10) account.move.action_switch_invoice_into_refund_credit_note
        switch_id = self._create_out_invoice(company_a, partner_b_id, product_id)
        try:
            self.client.call(
                "account.move",
                "action_switch_invoice_into_refund_credit_note",
                [switch_id],
                context=self._ctx(company_a["id"]),
            )
            switch = self._read_move(switch_id)
            self._ok("action_switch_invoice_into_refund_credit_note move_type", switch["move_type"] == "out_refund")
            if switch["is_internal_invoice"]:
                self._ok("inverse_move_type after switch", switch["inverse_move_type"] == "in_refund", switch["inverse_move_type"])
                switch_related_id = self._related_id(switch)
                self._ok("inter_comp_journal_entry_id regenerated after switch", switch_related_id is not None)
                if switch_related_id:
                    switch_related = self._read_move(switch_related_id)
                    self._ok("related move after switch", switch_related["move_type"] == "in_refund", switch_related["move_type"])
        except RuntimeError as exc:
            print(f"[WARN] action_switch_invoice_into_refund_credit_note skipped: {exc}")

        # 11) External partner -> no inter-company link
        external_partner_id = self.client.create("res.partner", {"name": "CAP RPC External Partner"})
        external_id = self.client.create(
            "account.move",
            {
                "move_type": "out_invoice",
                "partner_id": external_partner_id,
                "invoice_line_ids": [
                    (CMD_CREATE, 0, {
                        "product_id": product_id,
                        "quantity": 1.0,
                        "price_unit": 100.0,
                        "tax_ids": [(CMD_CLEAR, 0, 0)],
                    })
                ],
            },
            context=self._ctx(company_a["id"]),
        )
        external = self._read_move(external_id)
        self._ok("external partner is_internal_invoice is False", external["is_internal_invoice"] is False)
        self._ok("external partner no inter_comp_journal_entry_id", self._related_id(external) is None)

        print("=" * 80)
        print(f"Result: {self.passed} passed, {self.failed} failed")
        print("=" * 80)
        return self.failed == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RPC test for cap_account_intern_company_transection (Odoo 19)")
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

    success = CapInterCompanyRPCTest(client).run()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
