#!/usr/bin/env bash

# Test invoice and colour logic for Odoo project workflow
# -------------------------------------------------------
# This script performs the following steps:
#   1️⃣ Set company grace period (5 days)
#   2️⃣ Ensure a partner (qa_portal_customer@example.com) exists
#   3️⃣ Ensure a project "QA Project – Invoice Test" linked to that partner exists
#   4️⃣ Create a posted invoice with a configurable due‑date offset (DUE_OFFSET)
#   5️⃣ Run the odoo‑project‑workflow script (no PDF) to update the project colour
#   6️⃣ Retrieve and display the project's colour index (Odoo uses 1=red, 2=orange, 3=yellow?, 10=green)
#
# Usage examples (run from the workspace directory):
#   ./test_invoice_color.sh -d -3   # overdue 3 days → orange (within grace)
#   ./test_invoice_color.sh -d 3    # due in 3 days   → green (future)
#   ./test_invoice_color.sh -d -10  # overdue 10 days → red (beyond grace)
#   ./test_invoice_color.sh -d 0    # due today        → orange
#
# Required environment variables (same as the workflow script):
#   ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD

set -euo pipefail

# Helpers for coloured output
info()   { echo -e "\e[34m[INFO]\e[0m $*"; }
success(){ echo -e "\e[32m[SUCCESS]\e[0m $*"; }
error()  { echo -e "\e[31m[ERROR]\e[0m $*"; }

# ---------------------------------------------------------------------
# Parse due‑date offset argument (default: 0 => today)
# ---------------------------------------------------------------------
DUE_OFFSET=0
while [[ $# -gt 0 ]]; do
  case $1 in
    -d|--due-offset)
        DUE_OFFSET="$2"
        shift 2
        ;;
    *)
        error "Unknown argument: $1"
        exit 1
        ;;
  esac
done

# ---------------------------------------------------------------------
# Verify required Odoo environment variables
# ---------------------------------------------------------------------
: "${ODOO_URL?Missing ODOO_URL}" 
: "${ODOO_DB?Missing ODOO_DB}" 
: "${ODOO_USER?Missing ODOO_USER}" 
: "${ODOO_PASSWORD?Missing ODOO_PASSWORD}" 

# Export offset for Python subprocesses
export DUE_OFFSET="$DUE_OFFSET"

# ---------------------------------------------------------------------
# 1️⃣ Prepare Odoo data (company, partner, project, invoice)
# ---------------------------------------------------------------------
python3 - <<PYSETUP
import os, datetime
import odoorpc

url = os.getenv('ODOO_URL').rstrip('/')
proto, host = url.split('://')
db = os.getenv('ODOO_DB')
user = os.getenv('ODOO_USER')
pwd = os.getenv('ODOO_PASSWORD')
offset = int(os.getenv('DUE_OFFSET'))

odoo = odoorpc.ODOO(host, protocol='jsonrpc+ssl', port=443, version='19.0')
odoo.login(db, user, pwd)

# Company – set grace period to 5 days
Company = odoo.env['res.company']
company_id = Company.search([], limit=1)[0]
Company.write(company_id, {'number_of_days_authorized_in_late': 5})
print('[SETUP] Company grace period = 5')

# Partner – reuse or create
partner_email = 'qa_portal_customer@example.com'
Partner = odoo.env['res.partner']
partner_ids = Partner.search([('email', '=', partner_email)])
partner_id = partner_ids[0] if partner_ids else Partner.create({'name': 'QA Portal Customer', 'email': partner_email})
print(f'[SETUP] Partner id={partner_id}')

# Project – reuse or create
proj_name = 'QA Project – Invoice Test'
Project = odoo.env['project.project']
proj_ids = Project.search([('name', '=', proj_name), ('partner_id', '=', partner_id)])
project_id = proj_ids[0] if proj_ids else Project.create({'name': proj_name, 'partner_id': partner_id})
print(f'[SETUP] Project id={project_id}')

# Invoice – create and post with due date = today + offset days
invoice_date = datetime.date.today()
due_date = invoice_date + datetime.timedelta(days=offset)
Invoice = odoo.env['account.move']
# Ensure a product exists for the invoice line – pick any existing product
Product = odoo.env['product.product']
prod_ids = Product.search([], limit=1)
product_id = prod_ids[0] if prod_ids else None
if not product_id:
    raise Exception('No product found in the system to use for invoice line')
invoice_vals = {
    'partner_id': partner_id,
    'move_type': 'out_invoice',
    'invoice_date': invoice_date.isoformat(),
    'invoice_date_due': due_date.isoformat(),
    'state': 'draft',
    'invoice_line_ids': [(0, 0, {'name': 'Test line', 'quantity': 1, 'price_unit': 100.0})],
}
invoice_id = Invoice.create(invoice_vals)
Invoice.action_post([invoice_id])
print(f'[SETUP] Invoice id={invoice_id} due={due_date}')
PYSETUP

# ---------------------------------------------------------------------
# 2️⃣ Run the workflow script to apply colour logic (no PDF report)
# ---------------------------------------------------------------------
info "Running Odoo project workflow to update colour..."
~/.openclaw/workspace/skills/odoo-project-workflow/scripts/run_odoo_project_workflow.sh \
    "QA Project – Invoice Test" \
    "qa_portal_customer@example.com" \
    "Analysis" \
    --no-report

# ---------------------------------------------------------------------
# 3️⃣ Fetch and display the project's colour index
# ---------------------------------------------------------------------
python3 - <<PYRESULT
import os
import odoorpc

url = os.getenv('ODOO_URL').rstrip('/')
proto, host = url.split('://')
odoo = odoorpc.ODOO(host, protocol='jsonrpc+ssl', port=443, version='19.0')
odoo.login(os.getenv('ODOO_DB'), os.getenv('ODOO_USER'), os.getenv('ODOO_PASSWORD'))

proj_name = 'QA Project – Invoice Test'
partner_email = 'qa_portal_customer@example.com'
Partner = odoo.env['res.partner']
partner_id = Partner.search([('email', '=', partner_email)], limit=1)[0]
Project = odoo.env['project.project']
proj_id = Project.search([('name', '=', proj_name), ('partner_id', '=', partner_id)], limit=1)[0]
proj = Project.read([proj_id], ['color', 'stage_id'])[0]
print(f'[RESULT] colour index={proj.get("color")}, stage_id={proj.get("stage_id")}')
PYRESULT

success "Test completed. Colour index mapping (default Odoo): 1=red, 2=orange, 3=yellow?, 10=green."
