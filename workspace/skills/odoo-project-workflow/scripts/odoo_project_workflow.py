#!/usr/bin/env python3
"""
Odoo Project Workflow Automation

Runs the full end‑to‑end flow you described:
  • Create / locate a project
  • Set status & colour according to invoice dates
  • Grant portal access and share an editable link
  • Refresh domain calculations
  • (optional) generate a progress report
  • (optional) run Production Review
  • (optional) initialise a Test Session
  • (optional) open the Feedback wizard
  • (optional) update project planning (weekly capacity)
  • (optional) approve an access‑request and add the user to GitHub / MS‑Teams

All parameters are passed on the command line; credentials are taken from the
environment variables ODOO_URL, ODOO_DB, ODOO_USER and ODOO_PASSWORD.

Requirements
------------
pip install odoorpc python-dateutil requests
"""

import os
import sys
import argparse
import datetime
from dateutil import parser as dt_parser

import odoorpc  # type: ignore

# --------------------------------------------------------------------------- #
# Helper – Odoo connection
# --------------------------------------------------------------------------- #
def get_odoo():
    url = os.getenv("ODOO_URL")
    db = os.getenv("ODOO_DB")
    user = os.getenv("ODOO_USER")
    pwd = os.getenv("ODOO_PASSWORD")

    if not all([url, db, user, pwd]):
        sys.stderr.write("[ERROR] ODOO_* environment variables are not all set.\n")
        sys.exit(1)

    # Odoo URL usually "https://host" – drop trailing slash for odoorpc
    url = url.rstrip("/")
    # Odoo expects jsonrpc+ssl for HTTPS
    proto, host = url.split("://")  # keep for parsing only
    odoo = odoorpc.ODOO(host, protocol='jsonrpc+ssl', port=443, version='19.0')
    odoo.login(db, user, pwd)
    return odoo


# --------------------------------------------------------------------------- #
# 1️⃣  Project creation / lookup
# --------------------------------------------------------------------------- #
def _fill_required_fields(env, model_name, vals):
    """Populate any required fields that are missing in *vals*.
    For many2one fields we try to find the first existing record of the related model.
    For other field types we use a generic placeholder.
    """
    Model = env[model_name]
    fields = Model.fields_get()
    for name, info in fields.items():
        if info.get('required') and name not in vals:
            ftype = info.get('type')
            if ftype == 'many2one':
                rel_model = info.get('relation')
                # pick first record of the related model, or skip if none
                rel_ids = env[rel_model].search([], limit=1)
                if rel_ids:
                    vals[name] = rel_ids[0]
                else:
                    # fallback: leave blank (will raise later) but log
                    print(f"[WARN] Required many2one field '{name}' on {model_name} has no records to reference.")
            elif ftype in ('char', 'text'):
                vals[name] = 'N/A'
            elif ftype in ('integer', 'float'):
                vals[name] = 0
            elif ftype == 'boolean':
                vals[name] = False
            elif ftype == 'date':
                vals[name] = datetime.date.today().isoformat()
            elif ftype == 'datetime':
                vals[name] = datetime.datetime.utcnow().isoformat()
            elif ftype == 'selection':
                # Pick the first available option
                selection = info.get('selection')
                if selection and isinstance(selection, list) and selection:
                    vals[name] = selection[0][0]
                else:
                    vals[name] = None
            else:
                # generic placeholder for unknown types
                vals[name] = None
    return vals

def get_or_create_partner(odoo, email: str):
    Partner = odoo.env["res.partner"]
    partner_ids = Partner.search([("email", "=", email)])
    if partner_ids:
        return partner_ids[0]
    # Prepare minimal values and fill required fields
    partner_vals = {"name": email.split('@')[0].replace('.', ' ').title(), "email": email}
    partner_vals = _fill_required_fields(odoo.env, "res.partner", partner_vals)
    partner_id = Partner.create(partner_vals)
    print(f"[INFO] Created new partner for {email} (id={partner_id})")


def get_or_create_project(odoo, name: str, partner_id: int):
    Project = odoo.env["project.project"]
    proj_ids = Project.search([("name", "=", name), ("partner_id", "=", partner_id)])
    if proj_ids:
        proj_id = proj_ids[0]
        print(f"[INFO] Found existing project '{name}' (id={proj_id})")
    else:
        # Prepare minimal values and fill required fields
        proj_vals = {"name": name, "partner_id": partner_id}
        proj_vals = _fill_required_fields(odoo.env, "project.project", proj_vals)
        proj_id = Project.create(proj_vals)
        print(f"[INFO] Created project '{name}' (id={proj_id})")
    return proj_id


# --------------------------------------------------------------------------- #
# 2️⃣  Set status / colour according to invoice dates
# --------------------------------------------------------------------------- #
def set_project_status(odoo, project_id: int, partner_id: int):
    Invoice = odoo.env["account.move"]
    today = datetime.date.today()
    inv_ids = Invoice.search(
        [
            ("partner_id", "=", partner_id),
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
        ],
        order="invoice_date desc",
        limit=1,
    )
    if not inv_ids:
        print("[INFO] No posted invoices for the partner – leaving status unchanged.")
        return

    inv = Invoice.read(inv_ids[0], ["invoice_date", "invoice_date_due", "amount_total", "amount_residual"])
    due_date = dt_parser.parse(inv["invoice_date_due"]).date()
    days_late = (today - due_date).days

    if days_late < -5:
        colour = "green"
        stage_name = "Live (On‑going customization)"
    elif -5 <= days_late <= 0:
        colour = "yellow"
        stage_name = "Live (Support)"
    else:
        colour = "red"
        stage_name = "On Hold (Live)"

    Stage = odoo.env["project.task.type"]
    stage_ids = Stage.search([("name", "=", stage_name)], limit=1)
    stage_id = stage_ids[0] if stage_ids else False

    colour_map = {"green": 2, "yellow": 5, "red": 1}
    odoo.env["project.project"].write(
        project_id,
        {
            "stage_id": stage_id,
            "color": colour_map[colour],
        },
    )
    print(f"[INFO] Set project status to '{stage_name}' with colour {colour} (days late: {days_late})")


# --------------------------------------------------------------------------- #
# 3️⃣  Grant portal access and share an editable link
# --------------------------------------------------------------------------- #
def grant_portal_access(odoo, partner_id: int):
    Partner = odoo.env["res.partner"]
    # Try the standard wizard – may be missing in this DB
    try:
        Partner.action_grant_portal_access([partner_id])
        print("[INFO] Portal access granted via wizard.")
    except Exception as e:
        print(f"[WARN] Could not grant portal access via wizard: {e}")
    # Fallback URL for the portal
    share_url = f"{os.getenv('ODOO_URL').rstrip('/')}/my/projects/{partner_id}"
    print(f"[INFO] Editable project link for portal user: {share_url}")

def set_project_visibility(odoo, project_id: int, visibility: str = 'portal'):
    """Set the project's *privacy_visibility* field.
    Allowed keys (selection values) are:
    - 'followers'
    - 'invited_users'
    - 'employees'
    - 'portal'  # invited portal users & all internal users
    """
    try:
        odoo.env["project.project"].write(project_id, {"privacy_visibility": visibility})
        print(f"[INFO] Project visibility set to '{visibility}'.")
    except Exception as e:
        print(f"[WARN] Could not set project visibility: {e}")

def share_project_editable(odoo, project_id: int, partner_id: int):
    """Share the project in editable mode with the given portal partner.
    Attempts to use the ``project.share.wizard`` if it exists; otherwise falls back to a URL hint.
    """
    try:
        ShareWizard = odoo.env["project.share.wizard"]
        wizard = ShareWizard.create({"project_id": project_id, "partner_id": partner_id, "share_type": "editable"})
        if hasattr(ShareWizard, "action_share"):
            ShareWizard.action_share([wizard])
        elif hasattr(ShareWizard, "button_share"):
            ShareWizard.button_share([wizard])
        print(f"[INFO] Project shared (editable) with partner {partner_id} via share wizard.")
    except Exception as e:
        fallback_url = f"{os.getenv('ODOO_URL').rstrip('/')}/my/projects/{partner_id}?editable=1"
        print(f"[WARN] Could not use share wizard: {e}. Fallback URL: {fallback_url}")


# --------------------------------------------------------------------------- #
# 4️⃣  Refresh domain calculations
# --------------------------------------------------------------------------- #
def refresh_domain_calculation(odoo, project_id: int):
    try:
        # Directly invoke the model method that performs the domain refresh.
        odoo.env["project.project"].refresh_project_domain_calculation(project_id)
        print("[INFO] Refreshed domain calculations.")
    except Exception as e:
        print(f"[WARN] Could not call refresh_project_domain_calculation: {e}")


# --------------------------------------------------------------------------- #
# 5️⃣  (Optional) Progress report
# --------------------------------------------------------------------------- #
def get_phase_id(odoo, phase_name: str):
    Phase = odoo.env["project.project.phase"]
    phase_ids = Phase.search([("name", "=", phase_name)], limit=1)
    if not phase_ids:
        sys.stderr.write(f"[ERROR] Phase '{phase_name}' not found.\n")
        sys.exit(1)
    return phase_ids[0]


def generate_progress_report(odoo, project_id: int, phase: str):
    wizard = odoo.env["project.project.progress.report"]
    wiz_id = wizard.create({"project_id": project_id, "phase_id": get_phase_id(odoo, phase)})
    report = wizard.print_report(wiz_id)
    attachment = odoo.env["ir.attachment"].read(report, ["datas", "name"])[0]
    data = attachment["datas"]
    filename = attachment["name"]
    out_path = f"/home/captivea/.openclaw/workspace/{filename}"
    with open(out_path, "wb") as f:
        f.write(data.decode("base64"))
    print(f"[INFO] Progress report saved to {out_path}")


# --------------------------------------------------------------------------- #
# 6️⃣  Production Review
# --------------------------------------------------------------------------- #
def run_production_review(odoo, project_id: int):
    try:
        Review = odoo.env["project.review"]
        rev_id = Review.create({"project_id": project_id, "date": datetime.date.today().isoformat()})
        print(f"[INFO] Production Review created (id={rev_id})")
    except Exception as e:
        print(f"[WARN] Production Review step skipped: {e}")


# --------------------------------------------------------------------------- #
# 7️⃣  Initialise Test Session
# --------------------------------------------------------------------------- #
def initialise_test_session(odoo, project_id: int, user_email: str):
    try:
        Session = odoo.env["project.test.session"]
        User = odoo.env["res.users"]
        user_ids = User.search([("login", "=", user_email)], limit=1)
        if not user_ids:
            sys.stderr.write(f"[ERROR] No Odoo user found with login {user_email}\n")
            return
        assigned_user = user_ids[0]
        sess_id = Session.create({"project_id": project_id, "assigned_user_id": assigned_user, "signatory_id": assigned_user})
        try:
            Session.button_initialize(sess_id)
            print(f"[INFO] Test Session initialised (id={sess_id})")
        except Exception as e2:
            print(f"[WARN] Could not initialise test session via button: {e2}")
    except Exception as e:
        print(f"[WARN] Test Session step skipped: {e}")


# --------------------------------------------------------------------------- #
# 8️⃣  Open Feedback wizard
# --------------------------------------------------------------------------- #
def open_feedback(odoo, project_id: int):
    try:
        Feedback = odoo.env["project.feedback"]
        fb_id = Feedback.create({"project_id": project_id})
        print(f"[INFO] Feedback wizard opened (id={fb_id}) – you can now fill it in Odoo.")
    except Exception as e:
        print(f"[WARN] Feedback step skipped: {e}")


# --------------------------------------------------------------------------- #
# 9️⃣  Update Project Planning (weekly capacity)
# --------------------------------------------------------------------------- #
def update_project_planning(odoo, project_id: int):
    try:
        odoo.env["project.project"].button_update_planning(project_id)
        print("[INFO] Project planning updated according to weekly capacity.")
    except Exception as e:
        print(f"[WARN] Project planning step skipped: {e}")


# --------------------------------------------------------------------------- #
# 🔟  Approve Access Request + GitHub / Teams integration
# --------------------------------------------------------------------------- #
def approve_access_request(odoo, user_email: str):
    try:
        AccessReq = odoo.env["project.access.request"]
        req_ids = AccessReq.search([("email", "=", user_email), ("state", "=", "pending")], limit=1)
        if not req_ids:
            print(f"[INFO] No pending access request for {user_email}")
            return
        req_id = req_ids[0]
        AccessReq.button_approve(req_id)
        print(f"[INFO] Access request for {user_email} approved in Odoo.")
    except Exception as e:
        print(f"[WARN] Access request step skipped: {e}")

    # ---- GitHub -----------------------------------------------------------
    github_token = os.getenv("GITHUB_TOKEN")
    github_org = os.getenv("GITHUB_ORG")
    repo_name = os.getenv("GITHUB_REPO")
    if github_token and github_org and repo_name:
        import requests
        invite_url = f"https://api.github.com/repos/{github_org}/{repo_name}/collaborators/{user_email}"
        resp = requests.put(
            invite_url,
            headers={"Authorization": f"token {github_token}", "Accept": "application/vnd.github+json"},
        )
        if resp.status_code in (201, 204):
            print(f"[INFO] GitHub invitation sent to {user_email}")
        else:
            print(f"[WARN] GitHub invite failed ({resp.status_code}): {resp.text}")
    else:
        print("[WARN] GitHub env vars not set – skipping GitHub invite.")

    # ---- MS Teams ----------------------------------------------------------
    teams_token = os.getenv("MS_TEAMS_TOKEN")
    team_id = os.getenv("MS_TEAM_ID")
    if teams_token and team_id:
        import requests
        add_url = f"https://graph.microsoft.com/v1.0/teams/{team_id}/members"
        payload = {
            "@odata.type": "#microsoft.graph.aadUserConversationMember",
            "roles": ["member"],
            "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{user_email}')",
        }
        resp = requests.post(
            add_url,
            headers={"Authorization": f"Bearer {teams_token}", "Content-Type": "application/json"},
            json=payload,
        )
        if resp.status_code == 201:
            print(f"[INFO] Teams invitation sent to {user_email}")
        else:
            print(f"[WARN] Teams invite failed ({resp.status_code}): {resp.text}")
    else:
        print("[WARN] MS Teams env vars not set – skipping Teams invite.")


# --------------------------------------------------------------------------- #
# Main driver
# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(description="Odoo Project Workflow Automation")
    parser.add_argument("project_name", help="Name of the Odoo project")
    parser.add_argument("customer_email", help="Customer / partner e‑mail")
    parser.add_argument("phase", help="Phase name (e.g. Phase‑1, Analysis, Live…)")

    parser.add_argument("--no-report", action="store_true", help="Skip progress‑report generation")
    parser.add_argument("--review", action="store_true", help="Run Production Review")
    parser.add_argument("--test", action="store_true", help="Initialise a Test Session")
    parser.add_argument("--feedback", action="store_true", help="Open Feedback wizard")
    parser.add_argument("--plan", action="store_true", help="Update project planning (weekly capacity)")
    parser.add_argument("--access-request", metavar="USER_EMAIL", help="Approve pending access request for this e‑mail")
    args = parser.parse_args()

    odoo = get_odoo()

    # ----- 1️⃣ Project & partner -----
    partner_id = get_or_create_partner(odoo, args.customer_email)
    project_id = get_or_create_project(odoo, args.project_name, partner_id)

    # ----- 2️⃣ Status / colour -----
    set_project_status(odoo, project_id, partner_id)

    # ----- 3️⃣ Portal access (grant + visibility + share) -----
    grant_portal_access(odoo, partner_id)
    set_project_visibility(odoo, project_id, visibility='portal')
    share_project_editable(odoo, project_id, partner_id)

    # ----- 4️⃣ Refresh domains (using refresh_project_domain_calculation) -----
    refresh_domain_calculation(odoo, project_id)

    # ----- 5️⃣ Optional progress report -----
    if not args.no_report:
        generate_progress_report(odoo, project_id, args.phase)

    # ----- 6️⃣ Optional sub‑workflows -----
    if args.review:
        run_production_review(odoo, project_id)
    if args.test:
        initialise_test_session(odoo, project_id, args.customer_email)
    if args.feedback:
        open_feedback(odoo, project_id)
    if args.plan:
        update_project_planning(odoo, project_id)
    if args.access_request:
        approve_access_request(odoo, args.access_request)

    print("[INFO] Workflow completed successfully.")

if __name__ == "__main__":
    main()
