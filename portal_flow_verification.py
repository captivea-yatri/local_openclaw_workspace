#!/usr/bin/env python3
"""
Portal‑flow verification script for database odoo19_captivea2.
It creates a test partner, a portal user, enables the custom
`project_information` flag, links a demo project to that partner, and
checks that the portal user can see the project.
"""

import json, sys, xmlrpc.client
from urllib.parse import urljoin

# ----------------------------------------------------------------------
# Configuration (use the same credentials you used for other QA runs)
ODOO_URL = "https://aflutter-marxism-creamer.ngrok-free.dev"
DB       = "odoo19_captivea2"
USERNAME = "admin1"
PASSWORD = "a"
# ----------------------------------------------------------------------

def log(msg):
    print(msg)

def rpc_common():
    return xmlrpc.client.ServerProxy(urljoin(ODOO_URL, "/xmlrpc/2/common"))

def rpc_object():
    return xmlrpc.client.ServerProxy(urljoin(ODOO_URL, "/xmlrpc/2/object"))

def authenticate():
    uid = rpc_common().authenticate(DB, USERNAME, PASSWORD, {})
    if not uid:
        raise RuntimeError("Authentication failed")
    log(f"[+] Authenticated as UID={uid}")
    return uid, rpc_object()

def ensure_partner(models, uid):
    partners = models.execute_kw(
        DB, uid, PASSWORD,
        "res.partner", "search_read",
        [[("name", "=", "QA Portal Customer")]],
        {"fields": ["id"], "limit": 1},
    )
    if partners:
        pid = partners[0]["id"]
        log(f"[+] Test partner exists (ID={pid})")
        return pid
    pid = models.execute_kw(
        DB, uid, PASSWORD,
        "res.partner", "create",
        [{"name": "QA Portal Customer", "email": "qa_portal_test@example.com", "company_id": 1}],
    )
    log(f"[+] Created test partner (ID={pid})")
    return pid

def ensure_portal_user(models, uid, partner_id):
    users = models.execute_kw(
        DB, uid, PASSWORD,
        "res.users", "search_read",
        [[("partner_id", "=", partner_id), ("share", "=", True)]],
        {"fields": ["id"], "limit": 1},
    )
    if users:
        portal_uid = users[0]["id"]
        log(f"[+] Portal user already exists (UID={portal_uid})")
        return portal_uid
    portal_uid = models.execute_kw(
        DB, uid, PASSWORD,
        "res.users", "create",
        [{
            "name": "Portal QA Tester",
            "login": "qa_portal_test@example.com",
            "partner_id": partner_id,
            "share": True,
            "email": "qa_portal_test@example.com",
        }],
    )
    log(f"[+] Created portal user (UID={portal_uid})")
    return portal_uid

def enable_project_information(models, uid, partner_id):
    models.execute_kw(
        DB, uid, PASSWORD,
        "res.partner", "write",
        [[partner_id], {"project_information": True}],
    )
    log("[+] Enabled `project_information` on the test partner")

def get_or_create_demo_project(models, uid):
    proj = models.execute_kw(
        DB, uid, PASSWORD,
        "project.project", "search_read",
        [[("name", "=", "QA Portal Demo")]],
        {"fields": ["id"], "limit": 1},
    )
    if proj:
        pid = proj[0]["id"]
        log(f"[+] Using existing demo project (ID={pid})")
        return pid
    # create new demo project
    pid = models.execute_kw(
        DB, uid, PASSWORD,
        "project.project", "create",
        [{"name": "QA Portal Demo", "user_id": uid, "partner_id": 1}],
    )
    log(f"[+] Created demo project (ID={pid})")
    return pid

def link_project_to_partner(models, uid, project_id, partner_id):
    # The relation we use for portal visibility is the many2one field `partner_id`
    models.execute_kw(DB, uid, PASSWORD, "project.project", "write", [[project_id], {"partner_id": partner_id}])
    log(f"[+] Linked project {project_id} to partner {partner_id}")

def portal_user_visible_projects(models, portal_uid):
    # Portal view filters on partner_id == user.partner_id.id
    projects = models.execute_kw(
        DB, portal_uid, PASSWORD,
        "project.project", "search_read",
        [[("partner_id", "=", portal_uid)]],
        {"fields": ["name", "color", "on_hold_reason"], "limit": 20},
    )
    return projects

def main():
    uid_admin, models = authenticate()
    partner_id = ensure_partner(models, uid_admin)
    portal_uid = ensure_portal_user(models, uid_admin, partner_id)
    enable_project_information(models, uid_admin, partner_id)
    demo_proj_id = get_or_create_demo_project(models, uid_admin)
    link_project_to_partner(models, uid_admin, demo_proj_id, partner_id)
    log("\n[+] Querying portal‑visible projects for the portal user…")
    visible = portal_user_visible_projects(models, portal_uid)
    if not visible:
        log("[!] No projects returned – portal linking failed.")
    else:
        log(f"[+] Portal user sees {len(visible)} project(s):")
        for p in visible:
            log(f"    • {p['name']} (color={p['color']}, on_hold='{p.get('on_hold_reason') or ''}')")
        if any(p['name'] == 'QA Portal Demo' for p in visible):
            log("[✓] Demo project is correctly visible in the portal list.")
        else:
            log("[✗] Demo project NOT found – sharing may be mis‑configured.")
    # Save a detailed JSON for further analysis
    out_path = "/home/captivea/.openclaw/workspace/portal_flow_verification.json"
    with open(out_path, "w") as f:
        json.dump({
            "admin_uid": uid_admin,
            "partner_id": partner_id,
            "portal_user_id": portal_uid,
            "demo_project_id": demo_proj_id,
            "visible_projects": visible,
        }, f, indent=2)
    log(f"\n[+] Detailed JSON saved to: {out_path}")
    return 0 if visible else 1

if __name__ == "__main__":
    sys.exit(main())