#!/usr/bin/env python3
import json, xmlrpc.client, urllib.parse, time

ODOO_URL = "https://uriah-apolitical-masako.ngrok-free.dev"
DB = "odoo19_captivea2"
USERNAME = "cm@gmail.com"
PASSWORD = "a"

common = xmlrpc.client.ServerProxy(urllib.parse.urljoin(ODOO_URL.rstrip('/') + '/', 'xmlrpc/2/common'))
uid = common.authenticate(DB, USERNAME, PASSWORD, {})
if not uid:
    raise SystemExit('Authentication failed')
models = xmlrpc.client.ServerProxy(urllib.parse.urljoin(ODOO_URL.rstrip('/') + '/', 'xmlrpc/2/object'))

modules = [
    "res.partner",
    "crm.lead",
    "sale.order",
    "project.project",
    "go.live.change.request",
    "hr.timesheet",
    "account.move",
    "account.asset",
    "purchase.order",
    "hr.employee",
    "hr.goal",
    "hr.challenge",
    "hr.attendance",
    "hr.applicant",
    "helpdesk.ticket",
    "website.page",
    "marketing.campaign",
    "mail.mass_mailing",
    "social.post",
    "account.account",
    "account.analytic.account",
    "Timesheet",
    "hr.applicant",
    "hr.employee.public",
    "gamification.challenge",
    "gamification.goal",
    "account.journal",
    "account.payment",
    "account.tax",
    "product.template",
    "product.product",
    "project.task",
    "project.project.stage",
    "sale.order.line",
    "crm.stage",
    "crm.lost.reason",
    "product.pricelist",
    "website",
    "helpdesk.team",
    "social.media",
    "hr.attendance",
    "go.live.change.request",
    "hr.leave",
    "documents.document",
    "res.partner",
    "go.live.change.request",
    "account.move",
    "account.asset",
    "purchase.order",
    "hr.employee",
    "hr.goal",
    "hr.challenge",
    "hr.attendance",
    "hr.applicant",
    "helpdesk.ticket",
    "website.page",
    "marketing.campaign",
    "mail.mass_mailing",
    "social.post"
]

unique_modules = []
for m in modules:
    if m not in unique_modules:
        unique_modules.append(m)

results = []

def add(tc, module, status, detail=""):
    results.append({"tc": tc, "module": module, "action": "Read", "status": status, "detail": detail})

tc = 1
for mod in unique_modules:
    try:
        time.sleep(0.1)
        ids = models.execute_kw(DB, uid, PASSWORD, mod, 'search', [[]], {'limit': 1})
        add(tc, mod, "PASS", f"Found {len(ids)} records")
    except Exception as e:
        add(tc, mod, "FAIL", str(e))
    tc += 1

print(json.dumps(results, indent=2))
