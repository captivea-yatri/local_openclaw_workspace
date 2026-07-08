#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone RPC test — marketing_language & customer document language (Odoo 19).

Verifies that contact language settings flow through to sale orders, invoices,
and related customer documents.

No odoo-bin / shell required. Run with plain Python 3:

    python3 models/test_marketing_language_documents_rpc.py
    python3 models/test_marketing_language_documents_rpc.py --protocol xmlrpc
    python3 models/test_marketing_language_documents_rpc.py \\
        --url http://localhost:8069 --db odoo --user admin --password admin

Uses model/field names from:
  - models/res_partner.py   (marketing_language, lang)

Odoo standard behaviour (sale / account modules):
  - sale.order uses partner_id.lang for quotation PDFs and emails
  - account.move uses partner_id.lang for invoice PDFs and send emails

In cap_marketing_crm_automation, marketing_language is computed from lang:
  fr_* → fr | otherwise → en
So setting Language on the contact is what drives both marketing_language
and customer document language today.
"""
from __future__ import annotations

import argparse
import json
import sys
import xmlrpc.client
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

MODULE_NAME = "cap_marketing_crm_automation"

# ---------------------------------------------------------------------------
# Technical names from models/res_partner.py
# ---------------------------------------------------------------------------
MODEL_RES_PARTNER = "res.partner"
FIELD_MARKETING_LANGUAGE = "marketing_language"
FIELD_PARTNER_LANG = "lang"

LANG_FR = "fr_FR"
LANG_EN = "en_US"
MARKETING_FR = "fr"
MARKETING_EN = "en"

MODEL_SALE_ORDER = "sale.order"
MODEL_ACCOUNT_MOVE = "account.move"
MODEL_PRODUCT = "product.product"


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


class MarketingLanguageDocumentsRPCTest:
    """Test marketing_language → customer document language via RPC."""

    def __init__(self, client: OdooRPCClient):
        self.client = client
        self.passed = 0
        self.failed = 0
        self._cleanup_ids: dict[str, list[int]] = {
            MODEL_ACCOUNT_MOVE: [],
            MODEL_SALE_ORDER: [],
            MODEL_RES_PARTNER: [],
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

    def _skip(self, label: str, reason: str) -> None:
        print(f"[SKIP] {label} -> {reason}")

    def _m2o_id(self, value: Any) -> int | None:
        if not value:
            return None
        return value[0] if isinstance(value, (list, tuple)) else value

    def _track(self, model: str, record_id: int) -> None:
        if model in self._cleanup_ids:
            self._cleanup_ids[model].append(record_id)

    def _module_installed(self, name: str) -> bool:
        ids = self.client.search(
            "ir.module.module",
            [("name", "=", name), ("state", "=", "installed")],
        )
        return bool(ids)

    def _model_accessible(self, model: str) -> bool:
        try:
            self.client.fields_get(model, [])
            return True
        except RuntimeError:
            return False

    def _read_partner(self, partner_id: int) -> dict:
        return self.client.read(
            MODEL_RES_PARTNER,
            [partner_id],
            [FIELD_MARKETING_LANGUAGE, FIELD_PARTNER_LANG, "name"],
        )[0]

    def _document_lang_for_partner(self, partner_id: int) -> str:
        """Odoo uses partner.lang for SO/invoice PDFs and emails."""
        return self._read_partner(partner_id)[FIELD_PARTNER_LANG] or ""

    def _cleanup(self) -> None:
        for model in (MODEL_ACCOUNT_MOVE, MODEL_SALE_ORDER, MODEL_RES_PARTNER):
            ids = self._cleanup_ids.get(model, [])
            if ids:
                try:
                    self.client.unlink(model, ids)
                    print(f"  Cleaned up {len(ids)} {model} record(s)")
                except RuntimeError as exc:
                    print(f"  [WARN] cleanup {model} {ids}: {exc}")
            self._cleanup_ids[model] = []

    def _test_partner_language_mapping(self) -> tuple[int, int]:
        """Section 1: marketing_language mirrors contact lang (models/res_partner.py)."""
        print("\n--- Partner: marketing_language mapping ---")

        self._ok(
            f"Module {MODULE_NAME!r} installed",
            self._module_installed(MODULE_NAME),
        )
        self._ok(
            f"{MODEL_RES_PARTNER}.{FIELD_MARKETING_LANGUAGE} field exists",
            FIELD_MARKETING_LANGUAGE in self.client.fields_get(MODEL_RES_PARTNER, []),
        )

        fr_id = self.client.create(
            MODEL_RES_PARTNER,
            {"name": "RPC Doc Lang FR Customer", FIELD_PARTNER_LANG: LANG_FR},
        )
        self._track(MODEL_RES_PARTNER, fr_id)
        fr = self._read_partner(fr_id)
        self._ok(
            f"French contact lang={LANG_FR} → marketing_language=fr",
            fr[FIELD_PARTNER_LANG] == LANG_FR and fr[FIELD_MARKETING_LANGUAGE] == MARKETING_FR,
            f"lang={fr[FIELD_PARTNER_LANG]}, marketing_language={fr[FIELD_MARKETING_LANGUAGE]}",
        )

        en_id = self.client.create(
            MODEL_RES_PARTNER,
            {"name": "RPC Doc Lang EN Customer", FIELD_PARTNER_LANG: LANG_EN},
        )
        self._track(MODEL_RES_PARTNER, en_id)
        en = self._read_partner(en_id)
        self._ok(
            f"English contact lang={LANG_EN} → marketing_language=en",
            en[FIELD_PARTNER_LANG] == LANG_EN and en[FIELD_MARKETING_LANGUAGE] == MARKETING_EN,
            f"lang={en[FIELD_PARTNER_LANG]}, marketing_language={en[FIELD_MARKETING_LANGUAGE]}",
        )

        return fr_id, en_id

    def _test_lang_change_updates_marketing_language(self, partner_id: int) -> None:
        """Section 2: changing contact lang updates marketing_language."""
        print("\n--- Partner: lang change syncs marketing_language ---")

        self.client.write(MODEL_RES_PARTNER, [partner_id], {FIELD_PARTNER_LANG: LANG_FR})
        data = self._read_partner(partner_id)
        self._ok(
            "Switch lang to fr_FR updates marketing_language to fr",
            data[FIELD_PARTNER_LANG] == LANG_FR and data[FIELD_MARKETING_LANGUAGE] == MARKETING_FR,
        )

        self.client.write(MODEL_RES_PARTNER, [partner_id], {FIELD_PARTNER_LANG: LANG_EN})
        data = self._read_partner(partner_id)
        self._ok(
            "Switch lang to en_US updates marketing_language to en",
            data[FIELD_PARTNER_LANG] == LANG_EN and data[FIELD_MARKETING_LANGUAGE] == MARKETING_EN,
        )

    def _test_sale_order_document_language(self, fr_partner_id: int, en_partner_id: int) -> None:
        """Section 3: sale order documents use partner lang (Odoo sale module)."""
        print("\n--- Sale Order: document language ---")

        if not self._module_installed("sale"):
            self._skip("Sale order tests", "sale module not installed")
            return
        if not self._model_accessible(MODEL_SALE_ORDER):
            self._skip("Sale order tests", f"{MODEL_SALE_ORDER} not accessible")
            return

        product_ids = self.client.search(MODEL_PRODUCT, [("sale_ok", "=", True)], limit=1)
        if not product_ids:
            self._skip("Sale order tests", "no saleable product found")
            return

        product_id = product_ids[0]
        line_vals = {"product_id": product_id, "product_uom_qty": 1}

        so_fr_id = self.client.create(
            MODEL_SALE_ORDER,
            {"partner_id": fr_partner_id, "order_line": [(0, 0, line_vals)]},
        )
        self._track(MODEL_SALE_ORDER, so_fr_id)
        so_fr_partner_id = self._m2o_id(
            self.client.read(MODEL_SALE_ORDER, [so_fr_id], ["partner_id"])[0]["partner_id"]
        )
        doc_lang = self._document_lang_for_partner(so_fr_partner_id)
        self._ok(
            f"French customer SO uses partner lang {LANG_FR} for documents",
            doc_lang == LANG_FR,
            f"so id={so_fr_id}, document lang={doc_lang!r}",
        )

        so_en_id = self.client.create(
            MODEL_SALE_ORDER,
            {"partner_id": en_partner_id, "order_line": [(0, 0, line_vals)]},
        )
        self._track(MODEL_SALE_ORDER, so_en_id)
        so_en_partner_id = self._m2o_id(
            self.client.read(MODEL_SALE_ORDER, [so_en_id], ["partner_id"])[0]["partner_id"]
        )
        doc_lang = self._document_lang_for_partner(so_en_partner_id)
        self._ok(
            f"English customer SO uses partner lang {LANG_EN} for documents",
            doc_lang == LANG_EN,
            f"so id={so_en_id}, document lang={doc_lang!r}",
        )

    def _test_invoice_document_language(self, fr_partner_id: int, en_partner_id: int) -> None:
        """Section 4: invoice documents use partner lang (Odoo account module)."""
        print("\n--- Invoice: document language ---")

        if not self._module_installed("account"):
            self._skip("Invoice tests", "account module not installed")
            return
        if not self._model_accessible(MODEL_ACCOUNT_MOVE):
            self._skip("Invoice tests", f"{MODEL_ACCOUNT_MOVE} not accessible")
            return

        journal_ids = self.client.search(
            "account.journal",
            [("type", "=", "sale")],
            limit=1,
        )
        if not journal_ids:
            self._skip("Invoice tests", "no sale journal found")
            return

        inv_fr_id = self.client.create(
            MODEL_ACCOUNT_MOVE,
            {
                "move_type": "out_invoice",
                "partner_id": fr_partner_id,
                "journal_id": journal_ids[0],
            },
        )
        self._track(MODEL_ACCOUNT_MOVE, inv_fr_id)
        inv_fr = self.client.read(
            MODEL_ACCOUNT_MOVE, [inv_fr_id], ["partner_id"]
        )[0]
        doc_lang = self._document_lang_for_partner(self._m2o_id(inv_fr["partner_id"]))
        self._ok(
            f"French customer invoice uses partner lang {LANG_FR} for PDF/email",
            doc_lang == LANG_FR,
            f"invoice id={inv_fr_id}, document lang={doc_lang!r}",
        )

        inv_en_id = self.client.create(
            MODEL_ACCOUNT_MOVE,
            {
                "move_type": "out_invoice",
                "partner_id": en_partner_id,
                "journal_id": journal_ids[0],
            },
        )
        self._track(MODEL_ACCOUNT_MOVE, inv_en_id)
        inv_en = self.client.read(
            MODEL_ACCOUNT_MOVE, [inv_en_id], ["partner_id"]
        )[0]
        doc_lang = self._document_lang_for_partner(self._m2o_id(inv_en["partner_id"]))
        self._ok(
            f"English customer invoice uses partner lang {LANG_EN} for PDF/email",
            doc_lang == LANG_EN,
            f"invoice id={inv_en_id}, document lang={doc_lang!r}",
        )

    def _test_marketing_language_drives_documents(self, partner_id: int) -> None:
        """Section 5: full chain — lang → marketing_language → document language."""
        print("\n--- End-to-end: marketing_language → document language ---")

        self.client.write(MODEL_RES_PARTNER, [partner_id], {FIELD_PARTNER_LANG: LANG_FR})
        partner = self._read_partner(partner_id)
        doc_lang = self._document_lang_for_partner(partner_id)

        self._ok(
            "marketing_language=fr when lang=fr_FR",
            partner[FIELD_MARKETING_LANGUAGE] == MARKETING_FR,
        )
        self._ok(
            "document language matches marketing_language (fr → fr_FR)",
            partner[FIELD_MARKETING_LANGUAGE] == MARKETING_FR and doc_lang == LANG_FR,
            f"marketing_language={partner[FIELD_MARKETING_LANGUAGE]}, doc_lang={doc_lang!r}",
        )

        self.client.write(MODEL_RES_PARTNER, [partner_id], {FIELD_PARTNER_LANG: LANG_EN})
        partner = self._read_partner(partner_id)
        doc_lang = self._document_lang_for_partner(partner_id)

        self._ok(
            "marketing_language=en when lang=en_US",
            partner[FIELD_MARKETING_LANGUAGE] == MARKETING_EN,
        )
        self._ok(
            "document language matches marketing_language (en → en_US)",
            partner[FIELD_MARKETING_LANGUAGE] == MARKETING_EN and doc_lang == LANG_EN,
            f"marketing_language={partner[FIELD_MARKETING_LANGUAGE]}, doc_lang={doc_lang!r}",
        )

    def run(self) -> bool:
        print("=" * 80)
        print("Marketing Language → Customer Documents — RPC Test (Odoo 19)")
        print(f"Module : {MODULE_NAME}")
        print(
            f"Protocol: {self.client.protocol.upper()} | DB: {self.client.db} | URL: {self.client.url}"
        )
        print("=" * 80)

        fr_partner_id, en_partner_id = self._test_partner_language_mapping()
        self._test_lang_change_updates_marketing_language(en_partner_id)
        self._test_marketing_language_drives_documents(en_partner_id)
        self._test_sale_order_document_language(fr_partner_id, en_partner_id)
        self._test_invoice_document_language(fr_partner_id, en_partner_id)

        print("\n" + "=" * 80)
        print(f"Result: {self.passed} passed, {self.failed} failed")
        print("=" * 80)
        print(
            "\nNote: Odoo uses contact.lang for SO/invoice PDFs and emails.\n"
            "In this module, marketing_language is computed from lang, so set\n"
            "Language on the contact (or ensure lang is fr_FR / en_US) to control\n"
            "document language for that customer."
        )

        self._cleanup()
        return self.failed == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RPC test: marketing_language and customer document language (Odoo 19)",
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

    success = MarketingLanguageDocumentsRPCTest(client).run()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
