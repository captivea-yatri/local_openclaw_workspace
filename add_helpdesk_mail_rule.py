#!/usr/bin/env python3
"""
Create a dedicated mail.message record rule for the Helpdesk User group (id 406).
This gives Helpdesk users unrestricted read access to mail.message without adding them as followers.
"""
import json, sys, urllib.request

# --------------------------------------------------------------------------
# Configuration – adjust only if your environment differs
# --------------------------------------------------------------------------
BASE_URL = "https://2e22-2402-a00-152-5177-26af-425f-6ee5-72c0.ngrok-free.app"
DB       = "odoo19_captivea_june"
ADMIN_USER = "admin1"
ADMIN_PW   = "a"  # change if the admin password is different

# --------------------------------------------------------------------------
def jsonrpc(endpoint: str, payload: dict) -> dict:
    url = f"{BASE_URL}/{endpoint}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)

# --------------------------------------------------------------------------
# 1️⃣ Login as admin
# --------------------------------------------------------------------------
login_payload = {
    "jsonrpc": "2.0",
    "method": "call",
    "params": {"service": "common", "method": "login", "args": [DB, ADMIN_USER, ADMIN_PW]},
    "id": 1,
}
login_resp = jsonrpc("jsonrpc", login_payload)
admin_uid = login_resp.get("result")
if not admin_uid:
    print("❌ Admin login failed")
    sys.exit(1)
print(f"✅ Logged in as admin (uid={admin_uid})")

# --------------------------------------------------------------------------
# 2️⃣ Get ir.model.id for mail.message
# --------------------------------------------------------------------------
model_res = jsonrpc(
    "jsonrpc",
    {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [DB, admin_uid, ADMIN_PW, "ir.model", "search_read", [[{"model": "mail.message"}]], {"fields": ["id"], "limit": 1}],
        },
        "id": 2,
    },
)
if not model_res.get("result"):
    print("❌ Could not locate mail.message model")
    sys.exit(1)
mail_model_id = model_res["result"][0]["id"]
print(f"✅ mail.message model id = {mail_model_id}")

# --------------------------------------------------------------------------
# 3️⃣ Create the record rule for group 406 (Helpdesk User)
# --------------------------------------------------------------------------
rule_payload = {
    "jsonrpc": "2.0",
    "method": "call",
    "params": {
        "service": "object",
        "method": "execute_kw",
        "args": [
            DB,
            admin_uid,
            ADMIN_PW,
            "ir.rule",
            "create",
            [
                [
                    {
                        "name": "Helpdesk User – All Chatter (mail.message)",
                        "model_id": [mail_model_id, "mail.message"],
                        "domain_force": "[(1, '=', 1)]",
                        "global": False,
                        "groups": [(6, 0, [406])],
                        "perm_read": True,
                        "perm_write": False,
                        "perm_create": False,
                        "perm_unlink": False,
                    }
                ]
            ],
        ],
    },
    "id": 3,
}
create_resp = jsonrpc("jsonrpc", rule_payload)
if create_resp.get("error"):
    err = create_resp["error"]
    print(f"❌ Rule creation failed: {err.get('message')}")
    if err.get('data'):
        print('Details:', err['data'].get('debug'))
    sys.exit(1)
new_rule_id = create_resp["result"]
print(f"✅ New mail.message rule created – id = {new_rule_id}")

# --------------------------------------------------------------------------
# 4️⃣ Verify (optional)
# --------------------------------------------------------------------------
verify = jsonrpc(
    "jsonrpc",
    {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [
                DB,
                admin_uid,
                ADMIN_PW,
                "ir.rule",
                "search_read",
                [[{"id": new_rule_id}]],
                {"fields": ["name", "model_id", "domain_force", "global", "groups"]},
            ],
        },
        "id": 4,
    },
)
print("\n--- Created rule details -------------------------------------------------")
print(json.dumps(verify["result"], indent=2))
print("\n✅ Done. Log out/in as the Helpdesk user and reopen the ticket to see the full chatter.")
PY