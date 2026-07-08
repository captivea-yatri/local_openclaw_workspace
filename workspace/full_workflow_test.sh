#!/usr/bin/env bash

# Full Odoo Project Workflow Test
# --------------------------------
# This script creates three test projects, each with a different invoice due‑date
# offset, then exercises several core functionalities:
#   • Colour logic based on invoice due date (green/orange/red)
#   • Go‑Live date field update
#   • Generation of a Project Progress Report with a Signatory
#   • Setting a Project Stage and a Phase
#   • (optional) creating a Domain record (placeholder – adjust as needed)
#
# Prerequisites:
#   • Odoo credentials must be exported as environment variables:
#       ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD
#   • The "odoo‑project‑workflow" skill script must be present (it is used to
#     apply the colour logic).
#   • A product must exist in the database (the script will reuse the first
#     product it finds for invoice lines).
#
# Usage example:
#   ./full_workflow_test.sh
#
# The script prints a concise per‑project summary at the end.

set -euo pipefail

# ---------------------------------------------------------------------
# Helper output functions
# ---------------------------------------------------------------------
info()   { echo -e "\e[34m[INFO]\e[0m $*"; }
success(){ echo -e "\e[32m[SUCCESS]\e[0m $*"; }
error()  { echo -e "\e[31m[ERROR]\e[0m $*"; }

# ---------------------------------------------------------------------
# Verify required environment variables
# ---------------------------------------------------------------------
: "${ODOO_URL?Missing ODOO_URL}" 
: "${ODOO_DB?Missing ODOO_DB}" 
: "${ODOO_USER?Missing ODOO_USER}" 
: "${ODOO_PASSWORD?Missing ODOO_PASSWORD}" 

# ---------------------------------------------------------------------
# Configuration – three projects with three different invoice offsets
# ---------------------------------------------------------------------
PROJECTS=("QA Project – Full Test A" "QA Project – Full Test B" "QA Project – Full Test C")
# Offsets in days relative to today: negative = overdue, 0 = today, positive = future
OFFSETS=(-3 0 5)
PARTNER_EMAIL="qa_portal_customer@example.com"
SIGNATORY_LOGIN="admin1"   # will be used as report signatory
# Export variables so Python subprocesses can see them
export PARTNER_EMAIL SIGNATORY_LOGIN

# ---------------------------------------------------------------------
# Helper: run a python snippet with Odoo RPC (returns JSON via stdout)
# ---------------------------------------------------------------------
run_python(){
    python3 - <<PY
import os, sys, json, datetime
import odoorpc

url = os.getenv('ODOO_URL').rstrip('/')
proto, host = url.split('://')
db = os.getenv('ODOO_DB')
user = os.getenv('ODOO_USER')
pwd = os.getenv('ODOO_PASSWORD')
odoo = odoorpc.ODOO(host, protocol='jsonrpc+ssl', port=443, version='19.0')
odoo.login(db, user, pwd)

# expose helper objects to outer scope via globals()
globals()['odoo'] = odoo
PY
}

# ---------------------------------------------------------------------
# Obtain reusable IDs: partner, signatory user, first product, first stage
# ---------------------------------------------------------------------
info "Resolving reusable Odoo records…"
PY_RES=$(python3 - <<'PY'
import os, datetime
import odoorpc
url = os.getenv('ODOO_URL').rstrip('/')
proto, host = url.split('://')
odoo = odoorpc.ODOO(host, protocol='jsonrpc+ssl', port=443, version='19.0')
odoo.login(os.getenv('ODOO_DB'), os.getenv('ODOO_USER'), os.getenv('ODOO_PASSWORD'))
# Partner
Partner = odoo.env['res.partner']
partner_ids = Partner.search([('email', '=', os.getenv('PARTNER_EMAIL'))])
partner_id = partner_ids[0] if partner_ids else Partner.create({'name': 'QA Portal Customer', 'email': os.getenv('PARTNER_EMAIL')})
# Signatory (user)
User = odoo.env['res.users']
signatory_ids = User.search([('login', '=', os.getenv('SIGNATORY_LOGIN'))])
signatory_id = signatory_ids[0] if signatory_ids else None
# Product (first available)
Product = odoo.env['product.product']
prod_ids = Product.search([], limit=1)
product_id = prod_ids[0] if prod_ids else None
# Stage (first task type)
Stage = odoo.env['project.task.type']
stage_ids = Stage.search([], limit=1)
stage_id = stage_ids[0] if stage_ids else None
# Output JSON
import json, sys
out = {
    'partner_id': partner_id,
    'signatory_id': signatory_id,
    'product_id': product_id,
    'stage_id': stage_id,
}
print(json.dumps(out))
PY
)

if [[ -z "$PY_RES" ]]; then error "Failed to resolve base records"; exit 1; fi
partner_id=$(echo "$PY_RES" | jq -r '.partner_id')
signatory_id=$(echo "$PY_RES" | jq -r '.signatory_id')
product_id=$(echo "$PY_RES" | jq -r '.product_id')
stage_id=$(echo "$PY_RES" | jq -r '.stage_id')

if [[ -z "$partner_id" || "$partner_id" == "null" ]]; then error "Partner could not be created"; exit 1; fi
if [[ -z "$signatory_id" || "$signatory_id" == "null" ]]; then error "Signatory user not found"; exit 1; fi
if [[ -z "$product_id" || "$product_id" == "null" ]]; then error "No product found in DB"; exit 1; fi
if [[ -z "$stage_id" || "$stage_id" == "null" ]]; then error "No project stage found"; exit 1; fi

info "Partner=$partner_id, Signatory=$signatory_id, Product=$product_id, Stage=$stage_id"
export partner_id signatory_id product_id stage_id

# ---------------------------------------------------------------------
# Main loop – create projects, invoices, run workflow, generate report
# ---------------------------------------------------------------------
RESULTS=()
for i in "${!PROJECTS[@]}"; do
    proj_name="${PROJECTS[$i]}"
    offset="${OFFSETS[$i]}"
export offset
    info "--- Processing $proj_name (due offset = $offset) ---"

    # --- Create / fetch project ---
    PY_PROJ=$(python3 - <<PY
import os, datetime, json
import odoorpc
url = os.getenv('ODOO_URL').rstrip('/')
proto, host = url.split('://')
odoo = odoorpc.ODOO(host, protocol='jsonrpc+ssl', port=443, version='19.0')
odoo.login(os.getenv('ODOO_DB'), os.getenv('ODOO_USER'), os.getenv('ODOO_PASSWORD'))
Project = odoo.env['project.project']
proj_ids = Project.search([('name', '=', os.getenv('proj_name')), ('partner_id', '=', int(os.getenv('partner_id')))])
proj_id = proj_ids[0] if proj_ids else Project.create({'name': os.getenv('proj_name'), 'partner_id': int(os.getenv('partner_id'))})
print(json.dumps({'project_id': proj_id}))
PY
PY_PROJ)
project_id=$(echo "$PY_PROJ" | jq -r '.project_id')
export project_id
info "Project ID = $project_id"

    # --- Set Go‑Live date (30 days from today) ---
    PY_GO=$(python3 - <<PY
import os, datetime, json
import odoorpc
url = os.getenv('ODOO_URL').rstrip('/')
proto, host = url.split('://')
odoo = odoorpc.ODOO(host, protocol='jsonrpc+ssl', port=443, version='19.0')
odoo.login(os.getenv('ODOO_DB'), os.getenv('ODOO_USER'), os.getenv('ODOO_PASSWORD'))
Project = odoo.env['project.project']
proj_id = int(os.getenv('project_id'))
go_live_date = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
Project.write([proj_id], {'x_studio_go_live_date': go_live_date})
print(json.dumps({'go_live': go_live_date}))
PY
PY_GO)
info "Set Go‑Live date to $(echo $PY_GO | jq -r '.go_live')"

    # --- Create invoice with offset ---
    PY_INV=$(python3 - <<PY
import os, datetime, json
import odoorpc
url = os.getenv('ODOO_URL').rstrip('/')
proto, host = url.split('://')
odoo = odoorpc.ODOO(host, protocol='jsonrpc+ssl', port=443, version='19.0')
odoo.login(os.getenv('ODOO_DB'), os.getenv('ODOO_USER'), os.getenv('ODOO_PASSWORD'))
Invoice = odoo.env['account.move']
partner_id = int(os.getenv('partner_id'))
product_id = int(os.getenv('product_id'))
offset = int(os.getenv('offset'))
invoice_date = datetime.date.today()
due_date = invoice_date + datetime.timedelta(days=offset)
vals = {
    'partner_id': partner_id,
    'move_type': 'out_invoice',
    'invoice_date': invoice_date.isoformat(),
    'invoice_date_due': due_date.isoformat(),
    'state': 'draft',
    'invoice_line_ids': [(0, 0, {'name': 'Test line', 'quantity': 1, 'price_unit': 100.0})],
}
inv_id = Invoice.create(vals)
Invoice.action_post([inv_id])
print(json.dumps({'invoice_id': inv_id, 'due': due_date.isoformat()}))
PY
PY_INV)
invoice_id=$(echo "$PY_INV" | jq -r '.invoice_id')
info "Created invoice $invoice_id due $(echo $PY_INV | jq -r '.due')"

    # --- Run colour workflow (using existing skill script) ---
    info "Running colour workflow..."
    ~/.openclaw/workspace/skills/odoo-project-workflow/scripts/run_odoo_project_workflow.sh \
        "$proj_name" "$PARTNER_EMAIL" "Analysis" --no-report

    # --- Generate Project Progress Report with Signatory ---
    info "Creating Project Progress Report (signatory = $signatory_id)"
    PY_RPT=$(python3 - <<PY
import os, json
import odoorpc
url = os.getenv('ODOO_URL').rstrip('/')
proto, host = url.split('://')
odoo = odoorpc.ODOO(host, protocol='jsonrpc+ssl', port=443, version='19.0')
odoo.login(os.getenv('ODOO_DB'), os.getenv('ODOO_USER'), os.getenv('ODOO_PASSWORD'))
ReportWizard = odoo.env['project.project.progress.report']
proj_id = int(os.getenv('project_id'))
sign_id = int(os.getenv('signatory_id'))
wiz_id = ReportWizard.create({'project_id': proj_id, 'signatory_id': sign_id, 'phase_id': False})
# We won't print the PDF – just trigger the wizard to ensure it works
ReportWizard.button_print(wiz_id)
print(json.dumps({'wizard_id': wiz_id}))
PY
PY_RPT)
info "Progress report wizard created (ID=$(echo $PY_RPT | jq -r '.wizard_id'))"

    # --- Set Project Stage (using first stage we fetched earlier) ---
    info "Setting project stage to $stage_id"
    python3 - <<PY
import os
import odoorpc
url = os.getenv('ODOO_URL').rstrip('/')
proto, host = url.split('://')
odoo = odoorpc.ODOO(host, protocol='jsonrpc+ssl', port=443, version='19.0')
odoo.login(os.getenv('ODOO_DB'), os.getenv('ODOO_USER'), os.getenv('ODOO_PASSWORD'))
Project = odoo.env['project.project']
proj_id = int(os.getenv('project_id'))
stage_id = int(os.getenv('stage_id'))
Project.write([proj_id], {'stage_id': stage_id})
PY

    # --- Create a simple Phase (if not existing) and link to project ---
    info "Ensuring a Phase exists and linking to project"
    PY_PHASE=$(python3 - <<PY
import os, json
import odoorpc
url = os.getenv('ODOO_URL').rstrip('/')
proto, host = url.split('://')
odoo = odoorpc.ODOO(host, protocol='jsonrpc+ssl', port=443, version='19.0')
odoo.login(os.getenv('ODOO_DB'), os.getenv('ODOO_USER'), os.getenv('ODOO_PASSWORD'))
Phase = odoo.env['project.project.phase']
proj_id = int(os.getenv('project_id'))
# Try to find a phase named "Test Phase" for this project
phase_ids = Phase.search([('name', '=', 'Test Phase'), ('project_id', '=', proj_id)], limit=1)
if phase_ids:
    phase_id = phase_ids[0]
else:
    phase_id = Phase.create({'name': 'Test Phase', 'project_id': proj_id, 'weekly_capacity': 20})
print(json.dumps({'phase_id': phase_id}))
PY
PY_PHASE)
phase_id=$(echo "$PY_PHASE" | jq -r '.phase_id')
info "Phase ID = $phase_id"

    # --- (Optional) Create a Domain record – placeholder example ---
    info "Creating a dummy Domain linked to the project (if model exists)"
    python3 - <<PY
import os, json
import odoorpc
url = os.getenv('ODOO_URL').rstrip('/')
proto, host = url.split('://')
odoo = odoorpc.ODOO(host, protocol='jsonrpc+ssl', port=443, version='19.0')
odoo.login(os.getenv('ODOO_DB'), os.getenv('ODOO_USER'), os.getenv('ODOO_PASSWORD'))
Domain = odoo.env.get('project.domain')
if Domain:
    proj_id = int(os.getenv('project_id'))
    # create a simple domain if none exists for this project
    existing = Domain.search([('project_id', '=', proj_id)], limit=1)
    if not existing:
        Domain.create({'name': 'Test Domain', 'project_id': proj_id, 'status': 'not_started'})
PY

    # --- Record result for summary ---
    # Read colour field after workflow
    PY_COLOR=$(python3 - <<PY
import os, json
import odoorpc
url = os.getenv('ODOO_URL').rstrip('/')
proto, host = url.split('://')
odoo = odoorpc.ODOO(host, protocol='jsonrpc+ssl', port=443, version='19.0')
odoo.login(os.getenv('ODOO_DB'), os.getenv('ODOO_USER'), os.getenv('ODOO_PASSWORD'))
Project = odoo.env['project.project']
proj_id = int(os.getenv('project_id'))
proj = Project.read([proj_id], ['color', 'stage_id', 'x_studio_go_live_date'])
print(json.dumps({'color': proj[0].get('color'), 'stage_id': proj[0].get('stage_id'), 'go_live': proj[0].get('x_studio_go_live_date')}))
PY
PY_COLOR)
color=$(echo "$PY_COLOR" | jq -r '.color')
stage=$(echo "$PY_COLOR" | jq -r '.stage_id')
go_live=$(echo "$PY_COLOR" | jq -r '.go_live')
RESULTS+=("$proj_name | offset=$offset | colour=$color | stage=$stage | go_live=$go_live")

done

# ---------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------
info "=== Test Summary ==="
for line in "${RESULTS[@]}"; do
    echo "- $line"
done

success "Full workflow test completed."
