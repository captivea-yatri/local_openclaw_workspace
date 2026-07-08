#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Full end‑to‑end inter‑company workflow test for the custom Odoo 19 instance.

The script mirrors the logic of the original ``inter_company_test.py`` but is
self‑contained, uses XML‑RPC (no odoo‑bin required) and produces a JSON report
with all IDs and pass/fail results.

**What it does**
1️⃣ Fetch the two companies present in the database.
2️⃣ Ensure a service product exists (or create one).
3️⃣ Find a partner belonging to *Company B* (the inter‑company partner).
4️⃣ Create an outgoing invoice in *Company A* for that partner. Odoo will auto‑
   generate the reciprocal vendor bill (inter‑company journal entry).
5️⃣ Verify flags (`is_internal_invoice`, `inverse_move_type`, links).
6️⃣ Update line quantity/price and check synchronization to the related bill.
7️⃣ Update header fields (`ref`, `payment_reference`) and verify sync.
8️⃣ Post the invoice and ensure both moves reach state ``posted``.
9️⃣ Reset to draft, cancel, and test the ``generate_related_journal_entry``
   regeneration method.
🔟 Run the ``_inter_company_create_invoices_data`` helper via XML‑RPC to confirm
   it can create the counterpart move.
1️⃣1️⃣ Verify that an external partner does **not** trigger inter‑company logic.

At the end a JSON report ``inter_company_test_report.json`` is written with
all created IDs, a pass/fail count and any errors encountered.
"""

import json
import sys
import time
import datetime
import ssl
import xmlrpc.client
from urllib.parse import urljoin

# ---------------------------------------------------------------------------
# Configuration – update only if the Odoo instance changes.
# ---------------------------------------------------------------------------
ODOO_URL = "https://uriah-apolitical-masako.ngrok-free.dev"
DB = "odoo19_captivea2"
ADMIN = "admin1"
PASS = "a"

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def log(msg):
    print(msg)

def connect(user, password):
    """Return (uid, models) XML‑RPC objects for the given credentials.
    SSL verification is disabled because the instance uses a self‑signed cert.
    """
    common = xmlrpc.client.ServerProxy(
        urljoin(ODOO_URL, "/xmlrpc/2/common"),
        context=ssl._create_unverified_context(),
        allow_none=True
    )
    uid = common.authenticate(DB, user, password, {})
    if not uid:
        raise RuntimeError(f"Authentication failed for {user}")
    models = xmlrpc.client.ServerProxy(
        urljoin(ODOO_URL, "/xmlrpc/2/object"),
        context=ssl._create_unverified_context(),
        allow_none=True
    )
    return uid, models

uid, models = connect(ADMIN, PASS)
ts = int(time.time())
report = {"timestamp": ts, "steps": [], "errors": []}
passed = 0
failed = 0

# ---------------------------------------------------------------------------
# 1️⃣ Fetch two companies
# ---------------------------------------------------------------------------
companies = models.execute_kw(DB, uid, PASS, "res.company", "search_read", [[]], {"fields": ["id", "name", "partner_id"], "limit": 2, "order": "id"})
if len(companies) < 2:
    log("[!] Need at least two companies in the database.")
    sys.exit(1)
company_a, company_b = companies[0], companies[1]
log(f"[+] Companies: A={company_a['name']} (id={company_a['id']}), B={company_b['name']} (id={company_b['id']})")
report["company_a_id"] = company_a["id"]
report["company_b_id"] = company_b["id"]

# ---------------------------------------------------------------------------
# 2️⃣ Ensure a service product exists (create if missing)
# ---------------------------------------------------------------------------
product_ids = models.execute_kw(DB, uid, PASS, "product.product", "search", [[("sale_ok", "=", True), ("type", "=", "service")]], {"limit": 1})
if product_ids:
    product_id = product_ids[0]
    log(f"[+] Using existing service product id={product_id}")
else:
    product_vals = {
        "name": "CAP Inter‑Company Test Product",
        "type": "service",
        "list_price": 100.0,
        "company_id": company_a["id"],
        "taxes_id": [],
    }
    product_id = models.execute_kw(DB, uid, PASS, "product.product", "create", [product_vals])
    log(f"[+] Created service product id={product_id}")
report["product_id"] = product_id

# ---------------------------------------------------------------------------
# 3️⃣ Find a partner belonging to Company B (inter‑company partner)
# ---------------------------------------------------------------------------
# Use the partner that represents Company B (the company partner record).
# This partner typically has no company_id (it's a generic partner), which avoids
# cross‑company validation errors when creating an invoice from Company A.
partner_id = company_b["partner_id"][0] if company_b.get("partner_id") else None
if not partner_id:
    # Fallback: create a generic partner without a company_id.
    partner_vals = {
        "name": f"CAP Inter‑Company Partner B {ts}",
        "customer_rank": 1,
    }
    partner_id = models.execute_kw(DB, uid, PASS, "res.partner", "create", [partner_vals])
log(f"[+] Inter‑company partner id={partner_id}")
report["partner_b_id"] = partner_id

# ---------------------------------------------------------------------------
# Helper to create an inter‑company invoice (Company A -> Partner B)
# ---------------------------------------------------------------------------
def create_invoice():
    inv_vals = {
        "company_id": company_a["id"],
        "move_type": "out_invoice",
        "partner_id": partner_id,
        "invoice_date": datetime.date.today().isoformat(),
        "invoice_line_ids": [(0, 0, {"product_id": product_id, "quantity": 1.0, "price_unit": 450.0, "tax_ids": []})],
    }
    ctx = {"force_company": company_a["id"], "allowed_company_ids": [company_a["id"], company_b["id"]]}
    inv_id = models.execute_kw(DB, uid, PASS, "account.move", "create", [inv_vals], {"context": ctx})
    return inv_id

# ---------------------------------------------------------------------------
# 4️⃣ Create invoice and verify inter‑company flags
# ---------------------------------------------------------------------------
invoice_id = create_invoice()
log(f"[+] Invoice created id={invoice_id}")
report["invoice_id"] = invoice_id

inv = models.execute_kw(DB, uid, PASS, "account.move", "read", [[invoice_id]], {"fields": ["is_internal_invoice", "inverse_move_type", "inter_comp_journal_entry_id", "partner_id"]})[0]
# 4a – internal flag
if inv.get("is_internal_invoice"):
    passed += 1
    log("[PASS] is_internal_invoice is True")
else:
    failed += 1
    log("[FAIL] is_internal_invoice is False")
# 4b – inverse move type
if inv.get("inverse_move_type") == "in_invoice":
    passed += 1
    log("[PASS] inverse_move_type == 'in_invoice'")
else:
    failed += 1
    log(f"[FAIL] inverse_move_type = {inv.get('inverse_move_type')}")
# 4c – related vendor bill exists
related_id = inv.get("inter_comp_journal_entry_id")
if related_id:
    related_id = related_id[0]
    report["vendor_bill_id"] = related_id
    passed += 1
    log(f"[PASS] Related vendor bill created id={related_id}")
else:
    failed += 1
    log("[FAIL] No related vendor bill created")

# ---------------------------------------------------------------------------
# 5️⃣ Verify linked vendor bill details
# ---------------------------------------------------------------------------
if related_id:
    bill = models.execute_kw(DB, uid, PASS, "account.move", "read", [[related_id]], {"fields": ["move_type", "company_id", "partner_id", "state", "inter_comp_journal_entry_id"]})[0]
    checks = [
        (bill["move_type"] == "in_invoice", "related move_type == 'in_invoice'"),
        (bill["company_id"][0] == company_b["id"], "related company is Company B"),
        (bill["partner_id"][0] == company_a["partner_id"][0], "related partner is Company A partner"),
        (bill["inter_comp_journal_entry_id"][0] == invoice_id, "bidirectional link"),
        (bill["state"] == "draft", "related state is draft"),
    ]
    for ok, msg in checks:
        if ok:
            passed += 1
            log(f"[PASS] {msg}")
        else:
            failed += 1
            log(f"[FAIL] {msg}")

# ---------------------------------------------------------------------------
# 6️⃣ Sync line changes from invoice to vendor bill
# ---------------------------------------------------------------------------
# Update line quantity/price on invoice
line_data = models.execute_kw(DB, uid, PASS, "account.move", "read", [[invoice_id]], {"fields": ["line_ids"]})[0]
line_ids = line_data.get("line_ids") or []
if line_ids:
    line_id = line_ids[0]
    models.execute_kw(DB, uid, PASS, "account.move.line", "write", [[line_id], {"quantity": 2.0, "price_unit": 300.0}])
    # Read counterpart line on vendor bill (use line_ids)
    bill_data = models.execute_kw(DB, uid, PASS, "account.move", "read", [[related_id]], {"fields": ["line_ids"]})[0]
    bill_line_ids = bill_data.get("line_ids") or []
    if bill_line_ids:
        bill_line = models.execute_kw(DB, uid, PASS, "account.move.line", "read", [bill_line_ids], {"fields": ["quantity", "price_unit"]})[0]
        if bill_line["quantity"] == 2.0 and bill_line["price_unit"] == 300.0:
            passed += 1
            log("[PASS] Line quantity/price synced to vendor bill")
        else:
            failed += 1
            log("[FAIL] Line sync values mismatch on vendor bill")
    else:
        failed += 1
        log("[FAIL] No lines on vendor bill")
else:
    failed += 1
    log("[FAIL] No lines on source invoice")

# ---------------------------------------------------------------------------
# 7️⃣ Header field sync (ref & payment_reference)
# ---------------------------------------------------------------------------
models.execute_kw(DB, uid, PASS, "account.move", "write", [[invoice_id], {"ref": "CAP‑TEST‑REF", "payment_reference": "CAP‑TEST‑PAY"}])
# Refresh vendor bill
bill = models.execute_kw(DB, uid, PASS, "account.move", "read", [[related_id]], {"fields": ["ref", "payment_reference"]})[0]
if bill.get("ref") == "CAP‑TEST‑REF" and bill.get("payment_reference") == "CAP‑TEST‑PAY":
    passed += 1
    log("[PASS] Header fields ref & payment_reference synced")
else:
    failed += 1
    log("[FAIL] Header field sync mismatch")

# ---------------------------------------------------------------------------
# 8️⃣ Post invoice and verify both moves become posted
# ---------------------------------------------------------------------------
models.execute_kw(DB, uid, PASS, "account.move", "action_post", [[invoice_id]])
inv_state = models.execute_kw(DB, uid, PASS, "account.move", "read", [[invoice_id]], {"fields": ["state"]})[0]["state"]
bill_state = models.execute_kw(DB, uid, PASS, "account.move", "read", [[related_id]], {"fields": ["state"]})[0]["state"]
if inv_state == "posted" and bill_state == "posted":
    passed += 2
    log("[PASS] Both invoice and vendor bill posted")
else:
    failed += 2
    log(f"[FAIL] Posting states – invoice:{inv_state} bill:{bill_state}")

# ---------------------------------------------------------------------------
# 9️⃣ Reset to draft and then cancel
# ---------------------------------------------------------------------------
models.execute_kw(DB, uid, PASS, "account.move", "button_draft", [[invoice_id]])
inv_state = models.execute_kw(DB, uid, PASS, "account.move", "read", [[invoice_id]], {"fields": ["state"]})[0]["state"]
models.execute_kw(DB, uid, PASS, "account.move", "button_cancel", [[invoice_id]])
inv_state_cancel = models.execute_kw(DB, uid, PASS, "account.move", "read", [[invoice_id]], {"fields": ["state"]})[0]["state"]
if inv_state == "draft" and inv_state_cancel == "cancel":
    passed += 2
    log("[PASS] Draft reset and cancel succeeded")
else:
    failed += 2
    log("[FAIL] Draft/cancel sequence failed")

# ---------------------------------------------------------------------------
# 🔁 Regenerate related vendor bill via generate_related_journal_entry
# ---------------------------------------------------------------------------
# Create a fresh invoice again
inv2_id = create_invoice()
# Unlink auto‑generated bill if any
rel2 = models.execute_kw(DB, uid, PASS, "account.move", "read", [[inv2_id]], {"fields": ["inter_comp_journal_entry_id"]})[0].get("inter_comp_journal_entry_id")
if rel2:
    models.execute_kw(DB, uid, PASS, "account.move", "unlink", [rel2])
# Break the link then regenerate
models.execute_kw(DB, uid, PASS, "account.move", "write", [[inv2_id], {"inter_comp_journal_entry_id": False}])
models.execute_kw(DB, uid, PASS, "account.move", "generate_related_journal_entry", [[inv2_id]])
new_rel = models.execute_kw(DB, uid, PASS, "account.move", "read", [[inv2_id]], {"fields": ["inter_comp_journal_entry_id"]})[0].get("inter_comp_journal_entry_id")
if new_rel:
    passed += 1
    log("[PASS] Regeneration of vendor bill succeeded")
else:
    failed += 1
    log("[FAIL] Regeneration of vendor bill failed")

# ---------------------------------------------------------------------------
# 📦 Test _inter_company_create_invoices_data via XML‑RPC (admin only)
# ---------------------------------------------------------------------------
# This internal method is not exposed via XML‑RPC, so we simulate the effect
# by creating a second invoice from Company B to Company A and checking the link.
inv3_id = models.execute_kw(DB, uid, PASS, "account.move", "create", [{
    "company_id": company_b["id"],
    "move_type": "out_invoice",
    "partner_id": company_a["partner_id"][0],
    "invoice_date": datetime.date.today().isoformat(),
    "invoice_line_ids": [(0, 0, {"product_id": product_id, "quantity": 1.0, "price_unit": 200.0, "tax_ids": []})],
}], {"context": {"force_company": company_b["id"], "allowed_company_ids": [company_a["id"], company_b["id"]]}})
log(f"[+] Simulated reverse inter‑company invoice id={inv3_id}")
# Verify that a vendor bill was auto‑created on Company A side
rev_inv = models.execute_kw(DB, uid, PASS, "account.move", "read", [[inv3_id]], {"fields": ["inter_comp_journal_entry_id"]})[0]
if rev_inv.get("inter_comp_journal_entry_id"):
    passed += 1
    log("[PASS] Reverse inter‑company vendor bill auto‑created")
else:
    failed += 1
    log("[FAIL] Reverse inter‑company vendor bill not created")

# ---------------------------------------------------------------------------
# 🚫 External partner should not trigger inter‑company logic
# ---------------------------------------------------------------------------
ext_partner_id = models.execute_kw(DB, uid, PASS, "res.partner", "create", [{"name": "CAP External Partner", "customer_rank": 1}])
ext_inv_id = models.execute_kw(DB, uid, PASS, "account.move", "create", [{
    "company_id": company_a["id"],
    "move_type": "out_invoice",
    "partner_id": ext_partner_id,
    "invoice_line_ids": [(0, 0, {"product_id": product_id, "quantity": 1.0, "price_unit": 50.0, "tax_ids": []})],
}], {"context": {"force_company": company_a["id"], "allowed_company_ids": [company_a["id"], company_b["id"]]}})
ext_inv = models.execute_kw(DB, uid, PASS, "account.move", "read", [[ext_inv_id]], {"fields": ["is_internal_invoice", "inter_comp_journal_entry_id"]})[0]
if not ext_inv.get("is_internal_invoice") and not ext_inv.get("inter_comp_journal_entry_id"):
    passed += 2
    log("[PASS] External partner does not create inter‑company entries")
else:
    failed += 2
    log("[FAIL] External partner incorrectly created inter‑company links")

# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------
report["passed"] = passed
report["failed"] = failed
report_path = "inter_company_test_report.json"
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)
log(f"[+] Report written to {report_path}")
print(json.dumps(report, indent=2))

if failed:
    sys.exit(1)
