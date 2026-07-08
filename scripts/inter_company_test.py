#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Executable test script for Odoo inter‑company invoice & bill behaviour.
It creates an inter‑company invoice, checks the auto‑generated vendor bill,
ensures field sync, state transitions and the manual regeneration button.
The script is self‑contained and can be run directly (it uses the same
credentials as the previous manual script).
"""

import sys
import traceback
from datetime import date
# SUPERUSER_ID not needed for XML-RPC

try:
    import odoorpc
except ImportError:
    sys.stderr.write("Missing dependency 'odoorpc'. Install with: pip install odoorpc\n")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Connection configuration – replace with real credentials if needed.
# ---------------------------------------------------------------------------
ODOO_URL = "uriah-apolitical-masako.ngrok-free.dev"
DB_NAME = "odoo19_captivea2"
USERNAME = "admin1"
PASSWORD = "a"

import os
os.environ["ODOORPC_NO_SSL_VERIFY"] = "1"

odoo = odoorpc.ODOO(ODOO_URL, port=443, protocol="jsonrpc+ssl", version="19.0")
try:
    odoo.login(DB_NAME, USERNAME, PASSWORD)
except Exception as e:
    sys.stderr.write(f"Failed to authenticate to Odoo: {e}\n")
    sys.exit(1)

env = odoo.env

# Helper command tuples for one2many fields.
CMD_CREATE = lambda vals: (0, 0, vals)
CMD_UPDATE = lambda rec_id, vals: (1, rec_id, vals)

class InterCompanyTester:
    def __init__(self, env):
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

    def _setup(self):
        # Ensure we have at least two companies.
        company_ids = self.env["res.company"].search([], limit=2, order="id")
        if len(company_ids) < 2:
            raise RuntimeError("Need at least 2 companies in the database.")
        self.company_a, self.company_b = self.env["res.company"].browse(company_ids)
        print(f"Using companies: {self.company_a.name} (A) -> {self.company_b.name} (B)")
        # Get or create a service product.
        product_ids = self.env["product.product"].search([
            ("sale_ok", "=", True),
            ("type", "=", "service"),
        ], limit=1)
        if product_ids:
            self.product = self.env["product.product"].browse(product_ids)[0]
        else:
            prod_id = self.env["product.product"].create({
                "name": "CAP Manual Inter‑Company Product",
                "type": "service",
                "list_price": 100.0,
                "company_id": self.company_a.id,
                "taxes_id": [],
            })
            self.product = self.env["product.product"].browse([prod_id])[0]

    def _partner_of(self, company):
        # Find a partner belonging to the given company respecting allowed_company_ids.
        partner_ids = self.env["res.partner"].with_context(
            force_company=company.id,
            allowed_company_ids=[self.company_a.id, self.company_b.id],
        ).search([("company_id", "=", company.id)], limit=1)
        if not partner_ids:
            raise RuntimeError(f"No partner found for {company.name}")
        return self.env["res.partner"].with_context(
            force_company=company.id,
            allowed_company_ids=[self.company_a.id, self.company_b.id],
        ).browse(partner_ids)[0]

    def _create_invoice(self):
        # Create the invoice record without extra context.
        inv_id = self.env["account.move"].with_context(force_company=self.company_b.id).create({
            "company_id": self.company_b.id,
            "move_type": "out_invoice",
            "partner_id": self._partner_of(self.company_b).id,
            "invoice_date": date.today().isoformat(),
            "invoice_line_ids": [
                CMD_CREATE({
                    "product_id": self.product.id,
                    "name": "Manual inter‑company test line",
                    "quantity": 1.0,
                    "price_unit": 450.0,
                    "tax_ids": [],
                })
            ],
        })
        # Browse the newly created record to get a full Odoo model object.
        # Browse the record with a clean context to get full ORM methods.
        return self.env["account.move"].with_context().browse([inv_id])[0]

    def run(self):
        print("=" * 72)
        print("CAP Inter‑Company Transaction – automated test")
        print("=" * 72)
        self._setup()

        # 1. Create invoice and verify flags.
        invoice = self._create_invoice()
        # partner_id may be a list [id, name] from read(); extract name safely.
        partner_name = invoice.partner_id[1] if isinstance(invoice.partner_id, (list, tuple)) else getattr(invoice.partner_id, "display_name", "")
        self._ok(
            "is_internal_invoice is True for inter‑company partner",
            getattr(invoice, "is_internal_invoice", False),
            f"partner={partner_name}",
        )
        self._ok(
            "inverse_move_type is in_invoice",
            invoice.inverse_move_type == "in_invoice",
            f"got {invoice.inverse_move_type}",
        )

        # 2. Auto‑created vendor bill.
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

        # 3. Sync line changes.
        if related:
            invoice.write({
                "invoice_line_ids": [
                    CMD_UPDATE(invoice.invoice_line_ids[0].id, {"quantity": 2.0, "price_unit": 300.0})
                ]
            })
            line = related.invoice_line_ids[0]
            self._ok("Write syncs quantity", line.quantity == 2.0, f"qty={line.quantity}")
            self._ok("Write syncs price_unit", line.price_unit == 300.0, f"price={line.price_unit}")

        # 4. Header field sync.
        invoice.write({"ref": "CAP‑MANUAL‑REF", "payment_reference": "CAP‑MANUAL‑PAY"})
        if related:
            self._ok("Write syncs ref", related.ref == "CAP‑MANUAL‑REF")
            self._ok(
                "Write syncs payment_reference",
                related.payment_reference == "CAP‑MANUAL‑PAY",
            )

        # 5. Post sync.
        invoice.action_post()
        self._ok("Customer invoice posted", invoice.state == "posted")
        if related:
            self._ok("Related vendor bill posted", related.state == "posted")
            pr_lines = related.line_ids.filtered(
                lambda l: l.account_id.account_type in ("liability_payable", "asset_receivable")
            )
            self._ok(
                "Payable/receivable lines have due dates",
                not pr_lines or all(l.date_maturity for l in pr_lines),
            )

        # 6. Draft reset.
        invoice.button_draft()
        self._ok("Customer invoice draft", invoice.state == "draft")
        if related:
            self._ok("Related bill draft", related.state == "draft")

        # 7. Cancel sync.
        invoice.action_post()
        invoice.button_cancel()
        self._ok("Customer invoice cancelled", invoice.state == "cancel")
        if related:
            self._ok("Related bill cancelled", related.state == "cancel")

        # 8. Manual regenerate.
        invoice2 = self._create_invoice()
        related2 = invoice2.inter_comp_journal_entry_id
        if related2:
            related2.unlink()
        invoice2.write({"inter_comp_journal_entry_id": False})
        invoice2.generate_related_journal_entry()
        self._ok(
            "Regeneration recreates vendor bill",
            bool(invoice2.inter_comp_journal_entry_id),
        )
        if invoice2.inter_comp_journal_entry_id:
            self._ok(
                "Regenerated bill links back",
                invoice2.inter_comp_journal_entry_id.inter_comp_journal_entry_id.id == invoice2.id,
            )

        # 9. Account helper context flag.
        Account = self.env["account.account"]
        skipped = Account.with_context(from_inter_company_transaction=True)._get_most_frequent_account_for_partner(
            company_id=self.company_a.id,
            partner_id=self.company_b.partner_id.id,
            move_type="out_invoice",
        )
        self._ok(
            "Account suggestion skipped with context flag",
            skipped is False,
            f"got {skipped}",
        )

        # 10. External partner – should NOT create related bill.
        external = self.env["res.partner"].create({"name": "CAP External Partner Manual Test"})
        ext_ctx = {
            "force_company": self.company_a.id,
            "allowed_company_ids": [self.company_a.id, self.company_b.id],
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
        self._ok("External partner not internal invoice", not getattr(ext_invoice, "is_internal_invoice", False))
        self._ok("No related bill for external partner", not ext_invoice.inter_comp_journal_entry_id)

        print("=" * 72)
        print(f"Results: {self.passed} passed, {self.failed} failed")
        if self.errors:
            print("Failures:")
            for e in self.errors:
                print(f" - {e}")
        print("=" * 72)
        return self.failed == 0

if __name__ == "__main__":
    try:
        success = InterCompanyTester(env).run()
        if not success:
            sys.exit(1)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
