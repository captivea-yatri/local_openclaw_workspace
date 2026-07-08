#!/usr/bin/env python3
"""Run selected sub‑flows for an existing project (id 2028).
Uses the same Odoo connection logic as the official odoo_project_workflow script.
We will:
  1️⃣ Run Production Review
  2️⃣ Initialise a Test Session
  3️⃣ Open the Feedback wizard
  4️⃣ Generate a progress report (using the calculate_the_progress_remaining_hours method)
"""

import os, sys, datetime
import odoorpc  # type: ignore

# ---------------------------------------------------------------------------
# Configuration – same user as before
# ---------------------------------------------------------------------------
ODOO_URL = "https://uriah-apolitical-masako.ngrok-free.dev"
ODOO_DB = "odoo19_captivea2"
ODOO_USER = "nimesh@captivea.com"
ODOO_PASSWORD = "a"

os.environ["ODOO_URL"] = ODOO_URL
os.environ["ODOO_DB"] = ODOO_DB
os.environ["ODOO_USER"] = ODOO_USER
os.environ["ODOO_PASSWORD"] = ODOO_PASSWORD

def get_odoo():
    url = os.getenv("ODOO_URL").rstrip('/')
    proto, host = url.split('://')
    odoo = odoorpc.ODOO(host, protocol='jsonrpc+ssl', port=443, version='19.0')
    odoo.login(os.getenv("ODOO_DB"), os.getenv("ODOO_USER"), os.getenv("ODOO_PASSWORD"))
    return odoo

PROJECT_ID = 2028

odoo = get_odoo()

# ----- 1️⃣ Production Review -----
try:
    Review = odoo.env["project.review"]
    rev_id = Review.create({"project_id": PROJECT_ID, "date": datetime.date.today().isoformat()})
    print(f"[INFO] Production Review created (id={rev_id})")
except Exception as e:
    print(f"[WARN] Production Review step skipped: {e}")

# ----- 2️⃣ Initialise Test Session -----
try:
    Session = odoo.env["project.test.session"]
    User = odoo.env["res.users"]
    user_ids = User.search([("login", "=", ODOO_USER)], limit=1)
    if not user_ids:
        print(f"[ERROR] No Odoo user found for {ODOO_USER}")
        sys.exit(1)
    assigned = user_ids[0]
    sess_id = Session.create({"project_id": PROJECT_ID, "assigned_user_id": assigned, "signatory_id": assigned})
    try:
        Session.button_initialize(sess_id)
        print(f"[INFO] Test Session initialised (id={sess_id})")
    except Exception as e2:
        print(f"[WARN] Could not initialise test session via button: {e2}")
except Exception as e:
    print(f"[WARN] Test Session step skipped: {e}")

# ----- 3️⃣ Open Feedback wizard -----
try:
    Feedback = odoo.env["project.feedback"]
    fb_id = Feedback.create({"project_id": PROJECT_ID})
    print(f"[INFO] Feedback wizard opened (id={fb_id}) – fill it in Odoo UI.")
except Exception as e:
    print(f"[WARN] Feedback step skipped: {e}")

# ----- 4️⃣ Progress report (calculate_the_progress_remaining_hours) -----
try:
    # Create the wizard
    wizard_id = odoo.env["project.progress"].create({"project_id": PROJECT_ID})
    # Call the method that calculates remaining hours
    odoo.env["project.progress"].calculate_the_progress_remaining_hours([wizard_id])
    # Read the snapshot field (assumed to be 'snapshot_json')
    snapshot = odoo.env["project.progress"].read([wizard_id], ["snapshot_json"])[0].get('snapshot_json')
    print("[INFO] Progress report snapshot:")
    print(snapshot if snapshot else "No snapshot returned")
except Exception as e:
    print(f"[WARN] Progress report step failed: {e}")
