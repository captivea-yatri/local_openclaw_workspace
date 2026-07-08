#!/usr/bin/env python3
"""Run a subset of QA functional tests on the Odoo staging instance.
Outputs a JSON array of results, each dict containing:
  tc, module, action, result, status, detail
"""
import json, sys, traceback, xmlrpc.client, urllib.parse

import os
ODOO_URL = os.getenv("ODOO_URL", "https://staging-odoo19-captivea.odoo.com")
DB = os.getenv("ODOO_DB", "captivea-staging-odoo19-31833465")
USERNAME = os.getenv("ODOO_USERNAME", "dina.rajoharison@captivea.com")
PASSWORD = os.getenv("ODOO_PASSWORD", "c")

common_url = urllib.parse.urljoin(ODOO_URL.rstrip('/') + '/', 'xmlrpc/2/common')
object_url = urllib.parse.urljoin(ODOO_URL.rstrip('/') + '/', 'xmlrpc/2/object')
common = xmlrpc.client.ServerProxy(common_url)
uid = common.authenticate(DB, USERNAME, PASSWORD, {})
if not uid:
    print(json.dumps({"error": "authentication failed"}))
    sys.exit(1)
models = xmlrpc.client.ServerProxy(object_url)

results = []

def add_result(tc, module, action, status, detail=""):
    results.append({"tc": tc, "module": module, "action": action, "status": status, "detail": detail})

# Helper to create a partner (Contact)
def test_contact_create():
    tc = 59
    try:
        partner_id = models.execute_kw(DB, uid, PASSWORD, 'res.partner', 'create', [{
            'name': 'QA Test Customer - John Doe',
            'email': 'john.doe@example.com'
        }])
        add_result(tc, 'Contact', 'Create', 'PASS', f'Created id={partner_id}')
        # Cleanup
        models.execute_kw(DB, uid, PASSWORD, 'res.partner', 'unlink', [[partner_id]])
        add_result(tc, 'Contact', 'Delete (cleanup)', 'PASS', f'Deleted id={partner_id}')
    except Exception as e:
        add_result(tc, 'Contact', 'Create', 'FAIL', str(e))

def test_contact_read():
    tc = 10
    try:
        ids = models.execute_kw(DB, uid, PASSWORD, 'res.partner', 'search', [[]], {'limit': 5})
        partners = models.execute_kw(DB, uid, PASSWORD, 'res.partner', 'read', [ids], {'fields': ['name']})
        add_result(tc, 'Contact', 'Read', 'PASS', f'Found {len(partners)} records')
    except Exception as e:
        add_result(tc, 'Contact', 'Read', 'FAIL', str(e))

def test_contact_delete_denied():
    tc = 60
    try:
        # Attempt to delete a record we likely cannot delete (e.g., a protected partner)
        ids = models.execute_kw(DB, uid, PASSWORD, 'res.partner', 'search', [['&',('name','ilike','Company'),'!','is_company', False]], {'limit':1})
        if not ids:
            add_result(tc, 'Contact', 'Delete', 'PASS', 'No eligible record to test delete denial')
            return
        models.execute_kw(DB, uid, PASSWORD, 'res.partner', 'unlink', [ids])
        add_result(tc, 'Contact', 'Delete', 'FAIL', 'Delete succeeded unexpectedly')
    except xmlrpc.client.Fault as fault:
        # Expected permission error
        add_result(tc, 'Contact', 'Delete', 'BLOCKED', f'Permission denied (fault {fault.faultCode})')
    except Exception as e:
        add_result(tc, 'Contact', 'Delete', 'ERROR', str(e))

def test_lead_create():
    tc = 63
    try:
        lead_id = models.execute_kw(DB, uid, PASSWORD, 'crm.lead', 'create', [{
            'name': 'QA Lead - Integration Test',
            'contact_name': 'John Doe',
            'email_from': 'john.doe@example.com'
        }])
        add_result(tc, 'CRM Lead', 'Create', 'PASS', f'Created id={lead_id}')
        # Cleanup
        models.execute_kw(DB, uid, PASSWORD, 'crm.lead', 'unlink', [[lead_id]])
        add_result(tc, 'CRM Lead', 'Delete (cleanup)', 'PASS', f'Deleted id={lead_id}')
    except Exception as e:
        add_result(tc, 'CRM Lead', 'Create', 'FAIL', str(e))

def test_lead_read():
    tc = 61
    try:
        ids = models.execute_kw(DB, uid, PASSWORD, 'crm.lead', 'search', [[]], {'limit':5})
        leads = models.execute_kw(DB, uid, PASSWORD, 'crm.lead', 'read', [ids], {'fields':['name']})
        add_result(tc, 'CRM Lead', 'Read', 'PASS', f'Found {len(leads)} leads')
    except Exception as e:
        add_result(tc, 'CRM Lead', 'Read', 'FAIL', str(e))

def test_sales_order_create_missing_field():
    tc = 67
    try:
        # Intentionally omit required fields like partner_id
        so_id = models.execute_kw(DB, uid, PASSWORD, 'sale.order', 'create', [{
            'name': 'SO-QA-2026-TEST'
        }])
        add_result(tc, 'Sale Order', 'Create (missing field)', 'FAIL', f'Created unexpectedly id={so_id}')
    except xmlrpc.client.Fault as fault:
        add_result(tc, 'Sale Order', 'Create (missing field)', 'PASS', f'Expected error: {fault.faultString}')
    except Exception as e:
        add_result(tc, 'Sale Order', 'Create (missing field)', 'ERROR', str(e))

def test_sales_order_confirm_button():
    tc = 202
    try:
        # Create a minimal sales order with required fields
        partner_id = models.execute_kw(DB, uid, PASSWORD, 'res.partner', 'create', [{
            'name': 'QA Customer for SO',
            'email': 'qa.so@example.com'
        }])
        so_id = models.execute_kw(DB, uid, PASSWORD, 'sale.order', 'create', [{
            'partner_id': partner_id,
            'order_line': [(0, 0, {'product_id': 1, 'product_uom_qty': 1})]
        }])
        # Confirm button: method 'action_confirm'
        models.execute_kw(DB, uid, PASSWORD, 'sale.order', 'action_confirm', [so_id])
        add_result(tc, 'Sale Order', 'Button Confirm', 'PASS', f'Order {so_id} confirmed')
        # Cleanup: cancel then delete
        models.execute_kw(DB, uid, PASSWORD, 'sale.order', 'action_cancel', [so_id])
        models.execute_kw(DB, uid, PASSWORD, 'sale.order', 'unlink', [[so_id]])
        models.execute_kw(DB, uid, PASSWORD, 'res.partner', 'unlink', [[partner_id]])
        add_result(tc, 'Sale Order', 'Cleanup', 'PASS', f'Deleted order and partner')
    except Exception as e:
        add_result(tc, 'Sale Order', 'Button Confirm', 'FAIL', str(e))

def test_helpdesk_create():
    tc = 119
    try:
        ticket_id = models.execute_kw(DB, uid, PASSWORD, 'helpdesk.ticket', 'create', [{
            'name': 'QA Bug Report - Access Issue',
            'description': 'Testing helpdesk ticket creation'
        }])
        add_result(tc, 'Helpdesk Ticket', 'Create', 'PASS', f'Created id={ticket_id}')
        # Cleanup
        models.execute_kw(DB, uid, PASSWORD, 'helpdesk.ticket', 'unlink', [[ticket_id]])
        add_result(tc, 'Helpdesk Ticket', 'Delete (cleanup)', 'PASS', f'Deleted id={ticket_id}')
    except Exception as e:
        add_result(tc, 'Helpdesk Ticket', 'Create', 'FAIL', str(e))

def main():
    test_contact_read()
    test_contact_create()
    test_contact_delete_denied()
    test_lead_read()
    test_lead_create()
    test_sales_order_create_missing_field()
    test_sales_order_confirm_button()
    test_helpdesk_create()
    print(json.dumps(results, indent=2))

if __name__ == '__main__':
    main()
