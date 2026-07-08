#!/usr/bin/env python3
"""
Full portal‑user flow (from scratch) for database odoo19_captivea2.
Uses the existing portal login "portal@user.com" (password "a").
Steps:
1. Admin locates the portal user and its partner.
2. Enables the custom `project_information` flag on the partner.
3. Creates a new project linked to that partner.
4. Lists projects visible to the portal partner (admin‑side query).
5. Outputs a concise report and saves a detailed JSON file.
"""

import json, sys, xmlrpc.client
from urllib.parse import urljoin

# ----------------------------------------------------------------------
# Configuration – use the same admin credentials as before
ODOO_URL = "https://aflutter-marxism-creamer.ngrok-free.dev"
DB       = "odoo19_captivea2"
ADMIN_USER = "admin1"
ADMIN_PASS = "a"
PORTAL_LOGIN = "portal@user.com"
# ----------------------------------------------------------------------

def log(msg):
    print(msg)

def rpc_common():
    return xmlrpc.client.ServerProxy(urljoin(ODOO_URL, "/xmlrpc/2/common"))

def rpc_object():
    return xmlrpc.client.ServerProxy(urljoin(ODOO_URL, "/xmlrpc/2/object"))

def admin_auth():
    uid = rpc_common().authenticate(DB, ADMIN_USER, ADMIN_PASS, {})
    if not uid:
        raise RuntimeError("Admin authentication failed")
    log(f"[+] Admin authenticated (UID={uid})")
    return uid, rpc_object()

def find_portal_user(models, admin_uid):
    # Locate portal user by login
    users = models.execute_kw(
        DB, admin_uid, ADMIN_PASS,
        "res.users", "search_read",
        [[("login", "=", PORTAL_LOGIN)]],
        {"fields": ["id", "partner_id"]},
    )
    if not users:
        raise RuntimeError(f"Portal user {PORTAL_LOGIN} not found")
    uid = users[0]["id"]
    partner_id = users[0]["partner_id"][0]
    log(f"[+] Portal user found – UID={uid}, partner_id={partner_id}")
    return uid, partner_id

def enable_project_information(models, admin_uid, partner_id):
    models.execute_kw(
        DB, admin_uid, ADMIN_PASS,
        "res.partner", "write",
        [[partner_id], {"project_information": True}],
    )
    log("[+] Enabled `project_information` on portal partner")

def create_project(models, admin_uid, partner_id):
    proj_vals = {
        "name": "Portal User Full Test Project",
        "user_id": admin_uid,
        "partner_id": partner_id,
    }
    proj_id = models.execute_kw(DB, admin_uid, ADMIN_PASS, "project.project", "create", [proj_vals])
    log(f"[+] Created project (ID={proj_id}) linked to partner {partner_id}")
    return proj_id

def list_projects_for_partner(models, admin_uid, partner_id):
    projects = models.execute_kw(
        DB, admin_uid, ADMIN_PASS,
        "project.project", "search_read",
        [[("partner_id", "=", partner_id)]],
        {"fields": ["name", "color", "on_hold_reason"], "limit": 20},
    )
    return projects

def main():
    admin_uid, models = admin_auth()
    portal_uid, partner_id = find_portal_user(models, admin_uid)
    enable_project_information(models, admin_uid, partner_id)
    proj_id = create_project(models, admin_uid, partner_id)
    visible = list_projects_for_partner(models, admin_uid, partner_id)
    log("\n[+] Projects visible to portal partner:")
    for p in visible:
        log(f"    • {p['name']} (color={p['color']}, on_hold='{p.get('on_hold_reason') or ''}')")
    if any(p['id'] == proj_id for p in visible):
        log("[✓] Newly created project appears in portal‑visible list")
    else:
        log("[✗] New project NOT found in portal‑visible list")
    # Save detailed JSON
    out_path = "/home/captivea/.openclaw/workspace/portal_user_full_flow_from_scratch_report.json"
    with open(out_path, "w") as f:
        json.dump({
            "admin_uid": admin_uid,
            "portal_user_uid": portal_uid,
            "partner_id": partner_id,
            "created_project_id": proj_id,
            "visible_projects": visible,
        }, f, indent=2)
    log(f"\n[+] Detailed report saved to: {out_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())