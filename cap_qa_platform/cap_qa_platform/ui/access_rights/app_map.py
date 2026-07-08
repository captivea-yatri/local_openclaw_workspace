"""Map RPC smoke models to Odoo 19 UI apps and backend paths."""
from __future__ import annotations

# Mirrors SMOKE_MODELS_FIXED from test_access_rights_roles_rpc.py
UI_SMOKE_PROBES: list[dict[str, str]] = [
    {"model": "crm.lead", "app": "CRM", "path": "/odoo/crm"},
    {"model": "sale.order", "app": "Sales", "path": "/odoo/sales"},
    {"model": "res.partner", "app": "Contacts", "path": "/odoo/contacts"},
    {"model": "account.move", "app": "Accounting", "path": "/odoo/accounting"},
    {"model": "project.project", "app": "Project", "path": "/odoo/project"},
    {"model": "project.task", "app": "Project", "path": "/odoo/project"},
    {"model": "helpdesk.ticket", "app": "Helpdesk", "path": "/odoo/helpdesk"},
    {"model": "purchase.order", "app": "Purchase", "path": "/odoo/purchase"},
    {"model": "hr.expense", "app": "Expenses", "path": "/odoo/expenses"},
    {"model": "hr.applicant", "app": "Recruitment", "path": "/odoo/recruitment"},
    {"model": "account.analytic.line", "app": "Timesheets", "path": "/odoo/timesheet"},
    {"model": "gamification.goal", "app": "Goals", "path": "/odoo/goals"},
    {"model": "survey.survey", "app": "Surveys", "path": "/odoo/surveys"},
    {"model": "hr.employee", "app": "Employees", "path": "/odoo/employees"},
    {"model": "approval.request", "app": "Approvals", "path": "/odoo/approvals"},
]

ACCESS_DENIED_MARKERS = (
    "not allowed to access",
    "access error",
    "access denied",
    "you are not allowed",
)

PORTAL_MARKERS = ("/my",)
