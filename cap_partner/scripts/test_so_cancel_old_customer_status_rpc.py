#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone Odoo 19 RPC test for partner status transition on sale order
confirmation and cancellation.

Scenario:
1. Create a company partner.
2. Find an assistance offer (type='assistance').
3. Find two service products linked to that offer.
4. Create a sale order with the two lines and the offer.
5. Confirm the sale order → partner status should become 'customer'.
6. Run the "Create/Link Project" wizard (operation='create') → a project is
   created and linked to the sale order lines.
7. Cancel the sale order → partner status should become 'old_customer'.
8. Verify that no quality.issue.log records exist for the created project.

Usage:
    python3 cap_partner/scripts/test_so_cancel_old_customer_status_rpc.py \\
        --url https://staging-stag1-odoo19-captivea.odoo.com/ \\
        --db captivea-stag1-odoo19-33729640 \\
        --user divyesh \\
        --password 'a'

Environment variables (optional): ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD, ODOO_RPC
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.request
import xmlrpc.client
from datetime import datetime, timezone
from typing import Any

LOGGER = logging.getLogger(__name__)

DEFAULT_URL = "https://staging-stag1-odoo19-captivea.odoo.com/"
DEFAULT_DB = "captivea-stag1-odoo19-33729640"
DEFAULT_USER = "divyesh"
DEFAULT_PASSWORD = "a"


# ---------------------------------------------------------------------------
# RPC clients
# ---------------------------------------------------------------------------

class RpcError(Exception):
    """Odoo RPC fault / JSON-RPC error wrapper."""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


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

    def call(self, model, method, *args, **kwargs):
        clean_args = [sanitize_for_rpc(arg) for arg in args]
        clean_kwargs = sanitize_for_rpc(kwargs) if kwargs else {}
        return self.execute_kw(model, method, clean_args, clean_kwargs)

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

    def search_count(self, model, domain):
        return self.call(model, "search_count", domain)

    def read(self, model, ids, fields=None):
        if not ids:
            return []
        kw = {}
        if fields:
            kw["fields"] = fields
        return self.call(model, "read", ids, **kw)

    def create(self, model, vals):
        return self.call(model, "create", sanitize_for_rpc(vals))

    def write(self, model, ids, vals):
        return self.call(model, "write", ids, sanitize_for_rpc(vals))

    def unlink(self, model, ids):
        return self.call(model, "unlink", ids)

    def fields_get(self, model, attributes=None):
        kw = {}
        if attributes:
            kw["attributes"] = attributes
        return self.call(model, "fields_get", **kw)


class XmlRpcClient(OdooRpcClient):
    def authenticate(self):
        common = xmlrpc.client.ServerProxy(
            f"{self.url}/xmlrpc/2/common", allow_none=True,
        )
        self.uid = common.authenticate(self.db, self.login, self.password, {})
        if not self.uid:
            raise RpcError(f"Authentication failed for {self.login!r} on db {self.db!r}")
        self._models = xmlrpc.client.ServerProxy(
            f"{self.url}/xmlrpc/2/object", allow_none=True,
        )
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
# Test
# ---------------------------------------------------------------------------

def unique_suffix() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")[:15]


def sanitize_for_rpc(value):
    """Remove None values so XML-RPC can marshal Odoo command tuples."""
    if value is None:
        return False
    if isinstance(value, dict):
        return {k: sanitize_for_rpc(v) for k, v in value.items() if v is not None}
    if isinstance(value, (list, tuple)):
        return [sanitize_for_rpc(item) for item in value]
    return value


def m2o_id(value) -> int | None:
    if not value:
        return None
    if isinstance(value, (list, tuple)):
        return value[0]
    return value


class TestSaleOrderCancelOldCustomerStatus:
    def __init__(self, client: OdooRpcClient, no_cleanup: bool = False):
        self.rpc = client
        self.cleanup_tracker: list[tuple[str, int]] = []
        self.no_cleanup = no_cleanup
        self.suffix = unique_suffix()
        self.company_id: int | None = None
        self.team_id: int | False = False

    def _track(self, model: str, record_id: int):
        if not self.no_cleanup:
            self.cleanup_tracker.append((model, record_id))

    def _cleanup(self):
        for model, record_id in reversed(self.cleanup_tracker):
            if model == "sale.order":
                try:
                    rows = self.rpc.read("sale.order", [record_id], ["state"])
                    if rows and rows[0].get("state") in ("sale", "done"):
                        self.rpc.call("sale.order", "action_cancel", [record_id])
                except Exception as exc:
                    LOGGER.warning("[CLEANUP] Could not cancel sale.order %s: %s", record_id, exc)
        for model, record_id in reversed(self.cleanup_tracker):
            try:
                self.rpc.unlink(model, [record_id])
                LOGGER.info("[CLEANUP] Deleted %s %s", model, record_id)
            except Exception as exc:
                LOGGER.warning("[CLEANUP] Failed to delete %s %s: %s", model, record_id, exc)

    def run(self):
        self.authenticate()
        partner_id = self.create_partner()
        offer = self.find_assistance_offer()
        products = self.find_two_service_products(offer["id"])
        so_id = self.create_sale_order(partner_id, offer, products)
        self.confirm_sale_order(so_id)
        self.assert_partner_status(partner_id, "customer")
        project_id = self.create_link_project(so_id)
        self.assign_project_user(project_id)
        self.cancel_sale_order(so_id)
        self.assert_partner_status(partner_id, "old_customer")
        self.assert_no_quality_logs(project_id)
        LOGGER.info("[PASS] All assertions succeeded.")
        if not self.no_cleanup:
            self._cleanup()

    def authenticate(self):
        user = self.rpc.read("res.users", [self.rpc.uid], ["company_id"])[0]
        self.company_id = m2o_id(user.get("company_id"))
        if not self.company_id:
            raise RpcError("RPC user has no default company_id.")
        teams = self.rpc.search_read(
            "crm.team",
            [("company_id", "=", self.company_id)],
            ["id"],
            limit=1,
        )
        if not teams:
            teams = self.rpc.search_read(
                "crm.team",
                [("company_id", "=", False)],
                ["id"],
                limit=1,
            )
        self.team_id = teams[0]["id"] if teams else False
        LOGGER.info(
            "[INFO] Authenticated to Odoo as uid=%s company_id=%s team_id=%s",
            self.rpc.uid,
            self.company_id,
            self.team_id,
        )

    def create_partner(self) -> int:
        name = f"TestPartner_{self.suffix}"
        vals = {
            "name": name,
            "company_type": "company",
            "is_company": True,
            "company_id": self.company_id,
        }
        partner_id = self.rpc.create("res.partner", vals)
        self._track("res.partner", partner_id)
        LOGGER.info("[PASS] Created partner %s (id=%s)", name, partner_id)
        return partner_id

    def find_assistance_offer(self) -> dict[str, Any]:
        offer_fields = self.rpc.fields_get("offer.offer", attributes=["type"])
        type_field = None
        for candidate in ("type", "x_studio_type"):
            if candidate in offer_fields:
                type_field = candidate
                break

        offers = []
        if type_field:
            offers = self.rpc.search_read(
                "offer.offer",
                [(type_field, "=", "assistance")],
                ["id", "name", "business_unit_ids", "business_localisation_ids"],
                limit=1,
            )
        if not offers:
            offers = self.rpc.search_read(
                "offer.offer",
                [("name", "ilike", "assistance")],
                ["id", "name", "business_unit_ids", "business_localisation_ids"],
                limit=1,
            )
        if not offers:
            raise RpcError("Assistance offer not found.")
        offer = offers[0]
        LOGGER.info("[PASS] Found assistance offer id=%s name=%s", offer["id"], offer.get("name"))
        return offer

    def find_two_service_products(self, offer_id: int) -> list[dict[str, Any]]:
        domain = [
            ("offer_ids", "in", [offer_id]),
            ("type", "=", "service"),
            ("sale_ok", "=", True),
        ]
        fields = ["id", "name", "uom_id", "lst_price", "minimumSalePrice"]
        product_fields = self.rpc.fields_get("product.product", attributes=["type"])
        if "minimumSalePrice" not in product_fields:
            fields = [f for f in fields if f != "minimumSalePrice"]

        products = self.rpc.search_read("product.product", domain, fields, limit=2)
        if len(products) < 2:
            raise RpcError("Could not find two service products linked to the offer.")
        LOGGER.info("[PASS] Selected service products %s", [p["id"] for p in products])
        return products

    def _order_line_vals(self, product: dict[str, Any]) -> dict[str, Any]:
        uom_id = m2o_id(product.get("uom_id"))
        if not uom_id:
            raise RpcError(f"Product {product['id']} has no UoM.")
        price = product.get("lst_price") or 1.0
        minimum = product.get("minimumSalePrice")
        if minimum and price < minimum:
            price = minimum
        return {
            "product_id": product["id"],
            "product_uom_qty": 1.0,
            "product_uom_id": uom_id,
            "price_unit": price,
        }

    def create_sale_order(
        self,
        partner_id: int,
        offer: dict[str, Any],
        products: list[dict[str, Any]],
    ) -> int:
        bu_id = m2o_id(offer.get("business_unit_ids"))
        loc_id = m2o_id(offer.get("business_localisation_ids"))
        if not bu_id:
            bu_ids = offer.get("business_unit_ids") or []
            bu_id = bu_ids[0] if bu_ids else None
        if not loc_id:
            loc_ids = offer.get("business_localisation_ids") or []
            loc_id = loc_ids[0] if loc_ids else None
        if not bu_id or not loc_id:
            raise RpcError("Offer missing business unit or localisation.")

        order_vals = {
            "partner_id": partner_id,
            "company_id": self.company_id,
            "business_unit_id": bu_id,
            "business_localisation_id": loc_id,
            "offer_id": offer["id"],
            "order_line": [
                (0, 0, self._order_line_vals(products[0])),
                (0, 0, self._order_line_vals(products[1])),
            ],
        }
        if self.team_id:
            order_vals["team_id"] = self.team_id
        elif "team_id" in self.rpc.fields_get("sale.order", attributes=["type"]):
            order_vals["team_id"] = False
        so_id = self.rpc.create("sale.order", order_vals)
        self._track("sale.order", so_id)
        LOGGER.info("[PASS] Created sale.order id=%s", so_id)
        return so_id

    def confirm_sale_order(self, so_id: int):
        self.rpc.call("sale.order", "action_confirm", [so_id])
        LOGGER.info("[PASS] Sale order %s confirmed.", so_id)

    def cancel_sale_order(self, so_id: int):
        self.rpc.call("sale.order", "action_cancel", [so_id])
        LOGGER.info("[PASS] Sale order %s cancelled.", so_id)

    def assert_partner_status(self, partner_id: int, expected_status: str):
        partner = self.rpc.read("res.partner", [partner_id], ["status"])[0]
        actual = partner.get("status")
        if actual != expected_status:
            raise AssertionError(
                f"Partner status is '{actual}', expected '{expected_status}'."
            )
        LOGGER.info("[PASS] Partner %s status == '%s'", partner_id, expected_status)

    def _resolve_project_id(self, so_id: int) -> int | None:
        lines = self.rpc.search_read(
            "sale.order.line",
            [("order_id", "=", so_id)],
            ["project_id"],
        )
        for line in lines:
            project_id = m2o_id(line.get("project_id"))
            if project_id:
                return project_id

        so = self.rpc.read("sale.order", [so_id], ["partner_id"])[0]
        partner_id = m2o_id(so.get("partner_id"))
        projects = self.rpc.search(
            "project.project",
            [("partner_id", "=", partner_id)],
            limit=1,
            order="id desc",
        )
        return projects[0] if projects else None

    def create_link_project(self, so_id: int) -> int:
        wiz_id = self.rpc.create("link.so.project.wizard", {"operation": "create"})
        context = {
            "active_model": "sale.order",
            "active_id": so_id,
            "active_ids": [so_id],
        }
        self.rpc.call(
            "link.so.project.wizard",
            "link_so_project",
            [wiz_id],
            context=context,
        )
        LOGGER.info("[PASS] link_so_project wizard executed (wizard id=%s).", wiz_id)

        project_id = self._resolve_project_id(so_id)
        if not project_id:
            raise AssertionError("Project not linked to sale order after wizard.")

        self._track("project.project", project_id)
        LOGGER.info("[PASS] Project created with id=%s", project_id)
        return project_id

    def assign_project_user(self, project_id: int):
        self.rpc.write("project.project", [project_id], {"user_id": self.rpc.uid})
        project = self.rpc.read("project.project", [project_id], ["user_id"])[0]
        if m2o_id(project.get("user_id")) != self.rpc.uid:
            raise AssertionError(
                f"Project {project_id} user_id not set to RPC user {self.rpc.uid}."
            )
        LOGGER.info("[PASS] Project %s user_id set to %s", project_id, self.rpc.uid)

    def assert_no_quality_logs(self, project_id: int):
        count = self.rpc.search_count(
            "quality.issue.log",
            [("project_id", "=", project_id)],
        )
        if count != 0:
            raise AssertionError(
                f"Expected 0 quality.issue.log records for project {project_id}, found {count}."
            )
        LOGGER.info(
            "[PASS] No quality.issue.log records for project %s (count=%s)",
            project_id,
            count,
        )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Odoo RPC test: partner status after SO cancel",
    )
    parser.add_argument("--url", default=os.environ.get("ODOO_URL", DEFAULT_URL))
    parser.add_argument("--db", default=os.environ.get("ODOO_DB", DEFAULT_DB))
    parser.add_argument("--user", default=os.environ.get("ODOO_USER", DEFAULT_USER))
    parser.add_argument("--password", default=os.environ.get("ODOO_PASSWORD", DEFAULT_PASSWORD))
    parser.add_argument(
        "--rpc",
        choices=["xmlrpc", "jsonrpc"],
        default=os.environ.get("ODOO_RPC", "jsonrpc"),
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Do not delete created records after the test.",
    )
    return parser.parse_args()


def main():
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    args = parse_args()

    try:
        client = connect(args.url, args.db, args.user, args.password, rpc=args.rpc)
        test = TestSaleOrderCancelOldCustomerStatus(client, no_cleanup=args.no_cleanup)
        test.run()
    except RpcError as exc:
        LOGGER.error("[FAIL] RPC error: %s", exc)
        sys.exit(1)
    except AssertionError as exc:
        LOGGER.error("[FAIL] Assertion failed: %s", exc)
        sys.exit(1)
    except Exception as exc:
        LOGGER.exception("[FAIL] Unexpected error: %s", exc)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
