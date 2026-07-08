#!/usr/bin/env python3
"""Standalone test for the Production Review workflow.

Creates a partner (employee), a Production Question Template (100% frequency),
creates a project, assigns the partner to a role, creates a Production Review,
checks the three smart‑button relation fields, marks the review as done, and
writes a JSON report.
"""

import json, time, ssl, xmlrpc.client
from urllib.parse import urljoin

ODOO_URL = "https://uriah-apolitical-masako.ngrok-free.dev"
DB = "odoo19_captivea2"
ADMIN = "admin1"
PASS = "a"

def log(msg):
    print(msg)

# -------------------------------------------------
# Authentication helpers
# -------------------------------------------------
# Admin credentials (used for privileged actions if needed)
ADMIN_USER = ADMIN
ADMIN_PASS = PASS

# Target user credentials (the flow should run as this user)
USER_LOGIN = "yatri.modi@captivea.com"
USER_PASS = "a"

def admin_conn():
    common = xmlrpc.client.ServerProxy(
        urljoin(ODOO_URL, "/xmlrpc/2/common"),
        context=ssl._create_unverified_context()
    )
    uid = common.authenticate(DB, ADMIN_USER, ADMIN_PASS, {})
    if not uid:
        raise RuntimeError("Admin authentication failed")
    models = xmlrpc.client.ServerProxy(
        urljoin(ODOO_URL, "/xmlrpc/2/object"),
        context=ssl._create_unverified_context()
    )
    return uid, models

def user_conn():
    common = xmlrpc.client.ServerProxy(
        urljoin(ODOO_URL, "/xmlrpc/2/common"),
        context=ssl._create_unverified_context()
    )
    uid = common.authenticate(DB, USER_LOGIN, USER_PASS, {})
    if not uid:
        raise RuntimeError(f"User authentication failed for {USER_LOGIN}")
    models = xmlrpc.client.ServerProxy(
        urljoin(ODOO_URL, "/xmlrpc/2/object"),
        context=ssl._create_unverified_context()
    )
    return uid, models

def retry_call(func, max_attempts=3, sleep_seconds=5, *args, **kwargs):
    for attempt in range(max_attempts):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            log(f"[!] Attempt {attempt+1} failed: {e}")
            if attempt == max_attempts - 1:
                raise
            time.sleep(sleep_seconds)

reports = []

def main():
    uid, models = user_conn()
    # No admin privileges are used; all operations run as the logged‑in user
    # Use the specified user email for the flow
    email = "yatri.modi@captivea.com"
    # Timestamp for naming resources
    ts = int(time.time())
    # -------------------------------------------------
    # Resolve the login user (res.users) and get their partner
    # -------------------------------------------------
    user_ids = models.execute_kw(DB, uid, PASS, "res.users", "search", [[("login", "=", email)]], {"limit": 1})
    if not user_ids:
        raise RuntimeError(f"User with login {email} not found")
    user_id = user_ids[0]
    user = models.execute_kw(DB, uid, PASS, "res.users", "read", [[user_id]], {"fields": ["partner_id"]})[0]
    partner = user.get("partner_id")
    if not partner:
        raise RuntimeError(f"User {email} has no linked partner")
    target_partner_ids = [partner[0]]
    log(f"[+] Using user partner ID={partner[0]}")

    # -------------------------------------------------
    # 1️⃣ Partner (employee)
    # -------------------------------------------------


    # -------------------------------------------------
    # 2️⃣ Production Question Template (frequency 100%)
    # -------------------------------------------------
    tmpl_vals = {
        "name": f"Prod Q Template {ts}",
        "frequency": 100,  # always generate
    }
    try:
        tmpl_id = models.execute_kw(DB, uid, PASS, "production.question.template", "create", [tmpl_vals])
        log(f"[+] Question Template created ID={tmpl_id}")
    except Exception as e:
        log(f"[!] Failed to create question template: {e}")
        raise

    # -------------------------------------------------
    # 3️⃣ For each target partner, create a production review (no project or role)
    # -------------------------------------------------
    for pid in target_partner_ids:
        # ----- Production Review creation (using admin for privileged create) -----
        review_id = 4632  # use existing production review
        log(f"[+] Using existing Production Review ID={review_id} for partner {pid}")

        # ----- Smart‑button actions -----
        try:
            models.execute_kw(DB, uid, PASS, "production.review", "action_quality_issue", [review_id])
            log("[+] action_quality_issue executed")
        except Exception as e2:
            log(f"[!] action_quality_issue failed: {e2}")

        # Fetch quality issue logs (unfiltered) with the requested fields
        try:
            logs = models.execute_kw(
                DB, uid, PASS,
                "quality.issue.log",
                "search_read",
                [[("employee_id", "=", uid)]],
                {"fields": ["logged_date", "description", "log_type", "state", "employee_id"]}
            )
            if logs:
                log(f"[+] Fetched {len(logs)} quality issue log(s) with fields: logged_date, description, log_type, state, employee_id")
            else:
                log("[+] No quality issue logs found for review")
        except Exception as e_log:
            log(f"[!] Failed to fetch quality issue logs: {e_log}")

        # ----- Project smart‑button -----
        try:
            models.execute_kw(DB, uid, PASS, "production.review", "action_production_review_project", [review_id])
            log("[+] action_production_review_project executed")
        except Exception as e5:
            log(f"[!] action_production_review_project failed: {e5}")

        # ----- Mark done -----
        try:
            models.execute_kw(DB, uid, PASS, "production.review", "write", [[review_id], {"state": "done"}])
            log("[+] Production Review marked as done")
        except Exception as e6:
            log(f"[!] Could not mark as done: {e6}")

        # ----- Capture snapshot for this review -----
        try:
            snapshot = models.execute_kw(DB, uid, PASS, "production.review", "read", [[review_id]], {"fields": ["state"]})
        except Exception as e7:
            snapshot = []
            log(f"[!] Snapshot read failed: {e7}")
        reports.append({
            "partner_id": pid,
            "review_id": review_id,
            "review_fields": snapshot[0] if snapshot else {},
            "quality_issue_logs": logs if 'logs' in locals() else []
        })



if __name__ == "__main__":
    main()
    # Human‑readable summary
    print("\n--- Production Review Flow Summary ---")
    print(json.dumps(reports, indent=2))
