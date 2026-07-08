#!/usr/bin/env python3
"""Encrypt selected fields (email, phone, complete_name) on res.partner.
Uses the `field_database_encryption` module's wizard to encrypt existing data.
"""

import json, time, ssl, xmlrpc.client
from urllib.parse import urljoin

ODOO_URL = "https://aflutter-marxism-creamer.ngrok-free.dev"
DB       = "odoo19_captivea2"
ADMIN    = "admin1"
PASS     = "a"

def log(msg):
    print(msg)

def admin_conn():
    common = xmlrpc.client.ServerProxy(
        urljoin(ODOO_URL, "/xmlrpc/2/common"),
        context=ssl._create_unverified_context()
    )
    uid = common.authenticate(DB, ADMIN, PASS, {})
    if not uid:
        raise RuntimeError("Admin authentication failed")
    models = xmlrpc.client.ServerProxy(
        urljoin(ODOO_URL, "/xmlrpc/2/object"),
        context=ssl._create_unverified_context()
    )
    return uid, models

def main():
    uid, models = admin_conn()
    # 1️⃣ Find the field IDs for the three fields on res.partner
    field_names = ["email", "phone", "complete_name"]
    domain = [
        ("model", "=", "res.partner"),
        ("name", "in", field_names)
    ]
    field_ids = models.execute_kw(DB, uid, PASS, "ir.model.fields", "search", [domain])
    if not field_ids:
        raise RuntimeError("Could not locate the target fields")
    log(f"[+] Found field IDs {field_ids}")
    # 2️⃣ Mark them as encrypted (field_database_encryption respects the 'encrypted' flag)
    models.execute_kw(DB, uid, PASS, "ir.model.fields", "write", [[field_ids], {"encrypted": True}])
    log("[+] Marked fields as encrypted")

    # 3️⃣ Count how many partner records exist (to report)
    partner_count = models.execute_kw(DB, uid, PASS, "res.partner", "search_count", [[]])
    log(f"[+] res.partner has {partner_count} records")

    # 4️⃣ Run the encryption wizard for res.partner
    # The wizard method is provided by the module; name may vary – we use the common method.
    try:
        models.execute_kw(DB, uid, PASS,
                          "field_database_encryption", "encrypt_existing_data",
                          [["res.partner"]],  # model name list
                          {})
        log("[+] Encryption wizard completed for res.partner")
        success = True
    except Exception as e:
        log(f"[!] Encryption wizard failed: {e}")
        success = False

    # 5️⃣ Build report
    report = {
        "timestamp": int(time.time()),
        "model": "res.partner",
        "field_ids": field_ids,
        "partner_record_count": partner_count,
        "encryption_success": success,
    }
    report_path = "encrypt_res_partner_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    log(f"[+] Report written to {report_path}")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
