#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Remote inter‑company transaction test runner for Odoo 19.

Connects to the Odoo instance using XML‑RPC (odoorpc) with the credentials
provided by the user and runs the same functional checks that the original
`test_inter_company_manual.py` script performs when executed via
`odoo-bin shell`.

Prerequisites (install once):
    pip install odoorpc

Usage (run on any machine that can reach the ngrok URL):
    python3 test_inter_company_manual.py
"""

import sys
import traceback
from datetime import date

try:
    import odoorpc
except ImportError:
    sys.stderr.write("Missing dependency 'odoorpc'. Install with: pip install odoorpc\n")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Connection configuration – replace if you move the script elsewhere.
# ---------------------------------------------------------------------------
ODOO_URL = "uriah-apolitical-masako.ngrok-free.dev"
DB_NAME = "odoo19_captivea2"
USERNAME = "admin1"
PASSWORD = "a"

# The ngrok tunnel redirects HTTP → HTTPS, so we use the secure JSON‑RPC endpoint.
# Disable SSL verification for self‑signed certificates via environment variable.
import os
os.environ["ODOORPC_NO_SSL_VERIFY"] = "1"

# Use HTTPS (port 443) with the jsonrpc+ssl protocol.
odoo = odoorpc.ODOO(ODOO_URL, port=443, protocol="jsonrpc+ssl", version="19.0")
# (SSL verification disabled via ODOORPC_NO_SSL_VERIFY above)

try:
    odoo.login(DB_NAME, USERNAME, PASSWORD)
except Exception as e:
    sys.stderr.write(f"Failed to authenticate to Odoo: {e}\n")
    sys.exit(1)

# Helper shortcuts – these mirror the objects used in the original script.
env = odoo.env

# Odoo's many2one/one2many command tuples.
CMD_CREATE = lambda vals: (0, 0, vals)
CMD_UPDATE = lambda rec_id, vals: (1, rec_id, vals)
CMD_CLEAR = (5,)


class CapInterCompanyManualTester:
    def __init__(self, env):
        # The RPC env already runs with full access; no sudo needed.
        self.env = env
        self.passed = 0
        self.failed = 0
        self.errors = []

    def _ok(self, name, condition, detail=""):
        if condition:
            self.passed += 1
            print(f"[PASS] {name}")
            return True
        self.failed += 1
        msg = f"[FAIL] {name}" + (f" — {detail}" if detail else "")
        self.errors.append(msg)
        print(msg)
        return False

    def _setup_companies(self):
        # Search returns a list of IDs; we need record objects to access fields like .name.
        company_ids = self.env["res.company"].search([], limit=2, order="id")
        if len(company_ids) < 2:
            raise RuntimeError("Need at least 2 companies in the database.")
        # Browse converts IDs to record objects.
        companies = self.env["res.company"].browse(company_ids)
        self.company_a, self.company_b = companies[0], companies[1]
        print(f"Using companies: {self.company_a.name} (A) -> {self.company_b.name} (B)")
        # Search returns IDs; turn them into a record.
        product_ids = self.env["product.product"].search([
            ("sale_ok", "=", True),
            ("type", "=", "service"),
        ], limit=1)
        if product_ids:
            product = self.env["product.product"].browse(product_ids)[0]
        else:
            # Create a product explicitly tied to company A and without taxes.
            prod_id = self.env["product.product"].create({
                "name": "CAP Manual Inter-Company Product",
                "type": "service",
                "list_price": 100.0,
                "company_id": self.company_a.id,
                "taxes_id": [],
            })
            product = self.env["product.product"].browse([prod_id])[0]
        self.product = product

    def _global_partner(self):
        """Return a partner that is not tied to any company (company_id=False).
        If none exists, create a generic one called "CAP Global Partner".
        This partner can be used as the invoice partner to avoid cross‑company
        restrictions when the invoice's company differs from the partner's.
        """
        # Search for a partner with no company_id.
        partner_ids = self.env["res.partner"].search([("company_id", "=", False)], limit=1)
        if partner_ids:
            return self.env["res.partner"].browse(partner_ids)[0]
        # Create a fallback global partner.
        partner_id = self.env["res.partner"].create({
            "name": "CAP Global Partner",
            "company_id": False,
        })
        return self.env["res.partner"].browse([partner_id])[0]

    def _partner_of_company(self, company):
        # Retrieve a partner belonging to the given company, respecting allowed companies.
        # Use a generic search that works even if the default partner is not set.
        partner_ids = self.env["res.partner"].with_context(
            force_company=company.id,
            allowed_company_ids=[self.company_a.id, self.company_b.id],
        ).search([("company_id", "=", company.id)], limit=1)
        if not partner_ids:
            raise RuntimeError(f"No partner found for company {company.name}")
        # Browse with the same context to avoid allowed_company_ids restrictions.
        partner = self.env["res.partner"].with_context(
            force_company=company.id,
            allowed_company_ids=[self.company_a.id, self.company_b.id],
        ).browse(partner_ids)[0]
        return partner

    def _create_invoice(self):
        """Create an invoice belonging to Company B, using Company B's own partner.
        This avoids any cross‑company partner references.
        """
        ctx = {
            'force_company': self.company_b.id,
            'allowed_company_ids': [self.company_a.id, self.company_b.id],
        }
        inv_id = self.env["account.move"].with_context(**ctx).create({
            "company_id": self.company_b.id,
            "move_type": "out_invoice",
            "partner_id": self._partner_of_company(self.company_b).id,
            "invoice_date": date.today().isoformat(),
            "invoice_line_ids": [
                CMD_CREATE({
                    "product_id": self.product.id,
                    "name": "Manual inter-company test line",
                    "quantity": 1.0,
                    "price_unit": 450.0,
                    "tax_ids": [],
                })
            ],
        })
        return self.env["account.move"].browse([inv_id])[0]

    def run(self):
        print("=" * 72)
        print("CAP Inter-Company Transaction — manual test run")
        print("=" * 72)
        self._setup_companies()

        # 1) Internal invoice detection
        invoice = self._create_invoice()
        self._ok(
            "is_internal_invoice is True for inter-company partner",
            invoice.is_internal_invoice,
            f"partner={invoice.partner_id.display_name}",
        )
        self._ok(
            "inverse_move_type is in_invoice for customer invoice",
            invoice.inverse_move_type == "in_invoice",
            f"got {invoice.inverse_move_type}",
        )

        # 2) Auto-create related vendor bill on create
        related = invoice.inter_comp_journal_entry_id
        self._ok("Related vendor bill created on invoice create", bool(related))
        if related:
            self._ok("Related move type is vendor bill", related.move_type == "in_invoice")
            self._ok("Related bill company is Company B", related.company_id.id == self.company_b.id)
            self._ok(
                "Related bill partner is Company A",
                related.partner_id.id == self.company_a.partner_id.id,
            )
            self._ok(
                "Bidirectional link invoice <-> bill",
                related.inter_comp_journal_entry_id.id == invoice.id,
            )
            self._ok("Related bill starts in draft", related.state == "draft")

        # 3) Line sync on write
        if related:
            invoice.write({
                "invoice_line_ids": [
                    CMD_UPDATE(invoice.invoice_line_ids[0].id, {
                        "quantity": 2.0,
                        "price_unit": 300.0,
                    })
                ]
            })
            line = related.invoice_line_ids[0]
            self._ok("Write syncs quantity to related bill", line.quantity == 2.0, f"qty={line.quantity}")
            self._ok("Write syncs price_unit to related bill", line.price_unit == 300.0, f"price={line.price_unit}")

        # 4) Header field sync
        invoice.write({"ref": "CAP-MANUAL-REF", "payment_reference": "CAP-MANUAL-PAY"})
        if related:
            self._ok("Write syncs ref", related.ref == "CAP-MANUAL-REF", f"ref={related.ref}")
            self._ok(
                "Write syncs payment_reference",
                related.payment_reference == "CAP-MANUAL-PAY",
                f"payment_reference={related.payment_reference}",
            )

        # 5) Post sync
        invoice.action_post()
        self._ok("Customer invoice posted", invoice.state == "posted")
        if related:
            self._ok("Related vendor bill posted with customer invoice", related.state == "posted")
            pr_lines = related.line_ids.filtered(
                lambda l: l.account_id.account_type in ("liability_payable", "asset_receivable")
            )
            self._ok(
                "Payable/receivable lines have due dates on related bill",
                not pr_lines or all(l.date_maturity for l in pr_lines),
            )

        # 6) Reset to draft sync
        invoice.button_draft()
        self._ok("Customer invoice reset to draft", invoice.state == "draft")
        if related:
            self._ok("Related bill reset to draft", related.state == "draft")

        # 7) Cancel sync
        invoice.action_post()
        invoice.button_cancel()
        self._ok("Customer invoice cancelled", invoice.state == "cancel")
        if related:
            self._ok("Related bill cancelled", related.state == "cancel")

        # 8) Manual regenerate button
        invoice2 = self._create_invoice()
        related2 = invoice2.inter_comp_journal_entry_id
        if related2:
            related2.unlink()
        invoice2.write({"inter_comp_journal_entry_id": False})
        invoice2.generate_related_journal_entry()
        self._ok(
            "generate_related_journal_entry recreates vendor bill",
            bool(invoice2.inter_comp_journal_entry_id),
        )
        if invoice2.inter_comp_journal_entry_id:
            self._ok(
                "Regenerated bill links back to source invoice",
                invoice2.inter_comp_journal_entry_id.inter_comp_journal_entry_id.id == invoice2.id,
            )

        # 9) Account helper context flag
        Account = self.env["account.account"]
        skipped = Account.with_context(from_inter_company_transaction=True)._get_most_frequent_account_for_partner(
            company_id=self.company_a.id,
            partner_id=self.company_b.partner_id.id,
            move_type="out_invoice",
        )
        self._ok(
            "Account suggestion skipped with from_inter_company_transaction context",
            skipped is False,
            f"returned {skipped}",
        )

        # 10) External partner should not create related bill
        external = self.env["res.partner"].create({"name": "CAP External Partner Manual Test"})
        ext_ctx = {
            'force_company': self.company_a.id,
            'allowed_company_ids': [self.company_a.id, self.company_b.id],
        }
        ext_id = self.env["account.move"].with_context(**ext_ctx).create({
            "company_id": self.company_a.id,
            "move_type": "out_invoice",
            "partner_id": external.id,
            "invoice_line_ids": [
                CMD_CREATE({
                    "product_id": self.product.id,
                    "quantity": 1.0,
                    "price_unit": 50.0,
                })
            ],
        })
        ext_invoice = self.env["account.move"].browse([ext_id])[0]
        self._ok("External partner is not internal invoice", not ext_invoice.is_internal_invoice)
        self._ok("No related bill for external partner", not ext_invoice.inter_comp_journal_entry_id)

        print("=" * 72)
        print(f"Results: {self.passed} passed, {self.failed} failed")
        if self.errors:
            print("Failures:")
            for err in self.errors:
                print(f" - {err}")
        print("=" * 72)
        return self.failed == 0

if __name__ == "__main__":
    try:
        success = CapInterCompanyManualTester(env).run()
        if not success:
            sys.exit(1)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
