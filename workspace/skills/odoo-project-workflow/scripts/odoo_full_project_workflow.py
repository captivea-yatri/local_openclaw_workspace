#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Full Odoo Project Automation
================================

Creates a partner → project → runs every custom step you need.

All optional steps are enabled by default; you can turn any of them off
with the command‑line flags (e.g. `--no-report`, `--no-review`, etc.).

The script is defensive – if a model, field or button does not exist it
logs a warning and continues.
"""

import os, sys, argparse, datetime
from dateutil import parser as dt_parser
import odoorpc  # pip install odoorpc

# ---------------------------------------------------------------------------
# Helper – Odoo connection
# ---------------------------------------------------------------------------
def get_odoo():
    url = os.getenv("ODOO_URL")
    db = os.getenv("ODOO_DB")
    user = os.getenv("ODOO_USER")
    pwd = os.getenv("ODOO_PASSWORD")
    if not all([url, db, user, pwd]):
        sys.stderr.write("[ERROR] ODOO_* env vars not set\n")
        sys.exit(1)
    url = url.rstrip('/')
    host = url.split('://')[1]
    odoo = odoorpc.ODOO(host, protocol='jsonrpc+ssl', port=443, version='19.0')
    odoo.login(db, user, pwd)
    return odoo

# ---------------------------------------------------------------------------
# Partner handling
# ---------------------------------------------------------------------------
def get_or_create_partner(odoo, email: str):
    Partner = odoo.env['res.partner']
    partner_ids = Partner.search([('email', '=', email)])
    if partner_ids:
        return partner_ids[0]
    partner_id = Partner.create({
        'name': email.split('@')[0].replace('.', ' ').title(),
        'email': email,
    })
    print(f"[INFO] Created partner {email} (id={partner_id})")
    return partner_id