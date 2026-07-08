#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════════════════════=======
 ODOO FULL RBAC DISCOVERY & COMPARISON TOOL
════════════════════════════════════════════════════════════════════════=======

 Discovers EVERYTHING a user can access: all menus, all models, CRUD,
 field-level access, buttons/actions. Creates comprehensive baseline.

 PHASE 1 — DISCOVER v18.0:
 python3 odoo_rbac_tool.py discover --excel credentials.xlsx
 python3 odoo_rbac_tool.py discover --excel credentials.xlsx --roles "President,CEO"
 python3 odoo_rbac_tool.py discover --excel credentials.xlsx --test-connection
 python3 odoo_rbac_tool.py discover --excel credentials.xlsx --list-roles

 PHASE 2 — COMPARE v19.0:
 python3 odoo_rbac_tool.py compare --baseline baseline_v18_XXX.xlsx --excel creds_v19.xlsx

 REQUIREMENTS: pip install openpyxl requests
"""

import argparse, datetime, json, logging, os, re, sys, time, traceback
from collections import defaultdict, OrderedDict
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    sys.exit("pip install requests")
try:
    import openpyxl
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.formatting.rule import CellIsRule
except ImportError:
    sys.exit("pip install openpyxl")

TS = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = f"rbac_full_discovery_{TS}.log"

def setup_logging():
    lg = logging.getLogger("rbac")
    lg.setLevel(logging.DEBUG)
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s"))
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%H:%M:%S"))
    lg.addHandler(fh)
    lg.addHandler(ch)
    return lg

log = setup_logging()

def fix_url(url):
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"

def guess_db(url):
    h = urlparse(url).hostname or ""
    parts = h.split(".")
    return parts[0] if len(parts) >= 2 else ""

def norm_role(n):
    return re.sub(r'[\s_\-/()]+', '', n.lower().strip())

def match_roles(filters, available):
    am = {norm_role(n): n for n in available}
    matched, unmatch = set(), []
    for fn in filters:
        fn = fn.strip()
        if fn in available:
            matched.add(fn)
            continue
        fn_n = norm_role(fn)
        if fn_n in am:
            matched.add(am[fn_n])
            continue
        partial = [n for n in available if fn_n in norm_role(n)]
        if partial:
            matched.add(partial[0])
            continue
        unmatch.append(fn)
    return matched, unmatch

# ═══════════════════════════════════════════════════════════════
# KEY MODELS TO TEST (with create data and write fields)
# ═══════════════════════════════════════════════════════════════

KEY_MODELS = OrderedDict([
    ("res.partner", {"label": "Contacts", "create": {"name": "__RBAC_DISC__"}, "wfield": "phone", "wval": "0000"}),
    ("crm.lead", {"label": "CRM Leads", "create": {"name": "__RBAC_DISC__"}, "wfield": "description", "wval": "test"}),
    ("sale.order", {"label": "Sales Orders", "create": "auto", "wfield": "note", "wval": "test"}),
    ("project.project", {"label": "Projects", "create": {"name": "__RBAC_DISC__"}, "wfield": "description", "wval": "test"}),
    ("project.task", {"label": "Tasks", "create": {"name": "__RBAC_DISC__"}, "wfield": "description", "wval": "test"}),
    ("account.analytic.line", {"label": "Timesheets", "create": {"name": "__RBAC_DISC__", "unit_amount": 1.0}, "wfield": "name", "wval": "test"}),
    ("account.move", {"label": "Journal Entries", "create": "auto", "wfield": "narration", "wval": "test"}),
    ("account.asset", {"label": "Assets", "create": {"name": "__RBAC_DISC__"}, "wfield": "name", "wval": "__RBAC_DISC_W__"}),
    ("purchase.order", {"label": "Purchase Orders", "create": "auto", "wfield": "notes", "wval": "test"}),
    ("hr.employee", {"label": "Employees (Private)", "create": {"name": "__RBAC_DISC__"}, "wfield": "work_phone", "wval": "0000"}),
    ("hr.employee.public", {"label": "Employees (Public)", "create": "skip", "wfield": "auto", "wval": "test"}),
    ("gamification.goal", {"label": "Goals", "create": "skip", "wfield": "auto", "wval": "test"}),
    ("gamification.challenge", {"label": "Challenges", "create": {"name": "__RBAC_DISC__"}, "wfield": "description", "wval": "test"}),
    ("hr.attendance", {"label": "Attendance", "create": "skip", "wfield": "auto", "wval": "test"}),
    ("hr.applicant", {"label": "Recruitment", "create": {"partner_name": "__RBAC_DISC__"}, "wfield": "priority", "wval": "1"}),
    ("helpdesk.ticket", {"label": "Helpdesk Tickets", "create": {"name": "__RBAC_DISC__"}, "wfield": "description", "wval": "test"}),
    ("website", {"label": "Website", "create": "skip", "wfield": "auto", "wval": "test"}),
    ("marketing.activity", {"label": "Marketing Automation", "create": "skip", "wfield": "auto", "wval": "test"}),
    ("mailing.mailing", {"label": "Email Marketing", "create": {"subject": "__RBAC_DISC__"}, "wfield": "subject", "wval": "__RBAC_DISC_W__"}),
    ("social.post", {"label": "Social Marketing", "create": {"message": "__RBAC_DISC__"}, "wfield": "message", "wval": "__RBAC_DISC_W__"}),
    ("hr.leave", {"label": "Time Off", "create": "skip", "wfield": "auto", "wval": "test"}),
    ("hr.expense", {"label": "Expenses", "create": {"name": "__RBAC_DISC__"}, "wfield": "name", "wval": "__RBAC_DISC_W__"}),
    ("hr.contract", {"label": "Contracts", "create": "skip", "wfield": "name", "wval": "__RBAC_DISC_W__"}),
    ("hr.payslip", {"label": "Payslips", "create": "skip", "wfield": "auto", "wval": "test"}),
    ("approval.request", {"label": "Approvals", "create": {"name": "__RBAC_DISC__"}, "wfield": "name", "wval": "__RBAC_DISC_W__"}),
    ("fleet.vehicle", {"label": "Fleet", "create": "auto", "wfield": "auto", "wval": "test"}),
    ("lunch.order", {"label": "Lunch", "create": "skip", "wfield": "auto", "wval": "test"}),
    ("planning.slot", {"label": "Planning", "create": "skip", "wfield": "auto", "wval": "test"}),
    ("sign.request", {"label": "Sign Requests", "create": "skip", "wfield": "auto", "wval": "test"}),
    ("event.event", {"label": "Events", "create": {"name": "__RBAC_DISC__"}, "wfield": "name", "wval": "__RBAC_DISC_W__"}),
    ("survey.survey", {"label": "Surveys", "create": {"title": "__RBAC_DISC__"}, "wfield": "title", "wval": "__RBAC_DISC_W__"}),
    ("documents.document", {"label": "Documents", "create": {"name": "__RBAC_DISC__"}, "wfield": "name", "wval": "__RBAC_DISC_W__"}),
    ("hr.appraisal", {"label": "Appraisals", "create": "skip", "wfield": "auto", "wval": "test"}),
    ("account.payment", {"label": "Payments", "create": "skip", "wfield": "auto", "wval": "test"}),
    ("account.bank.statement", {"label": "Bank Statements", "create": {"name": "__RBAC_DISC__"}, "wfield": "name", "wval": "__RBAC_DISC_W__"}),
    ("product.template", {"label": "Products", "create": {"name": "__RBAC_DISC__"}, "wfield": "name", "wval": "__RBAC_DISC_W__"}),
])

# Buttons and fields checks follow... (trimmed for brevity)

# The rest of the script (OdooClient, FullDiscovery, generate_baseline, CompareEngine, main) is omitted for brevity.
# In a real deployment, include the full implementation as shown in the original source.

if __name__ == "__main__":
    main()
