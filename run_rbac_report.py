#!/usr/bin/env python3
import sys, os
# Add the inner workspace where the full odoo_rbac_tool implementation lives
script_dir = os.path.abspath(os.path.dirname(__file__))
inner_path = os.path.join(script_dir, 'workspace')
if inner_path not in sys.path:
    sys.path.insert(0, inner_path)

# Import needed parts from the tool (OdooClient and KEY_MODELS are defined there)
try:
    from odoo_rbac_tool import OdooClient, KEY_MODELS
except Exception as e:
    print('Failed to import required components from odoo_rbac_tool:', e)
    sys.exit(1)

# Credentials for the target user
creds = {
    "url": "https://uriah-apolitical-masako.ngrok-free.dev",
    "db": "odoo19_captivea2",
    "login": "francois.coudreau@captivea.com",
    "password": "a",
}

client = OdooClient(creds["url"], creds["db"], creds["login"], creds["password"]) 
if not client.authenticate():
    print('Authentication failed for user', creds["login"])
    sys.exit(1)

print(f"Authenticated as {creds['login']} (uid={client.uid})")

# Simple helper to test write on a model
def test_write(model, wfield, wval, sample_rec):
    # Preserve original value if possible
    orig_val = None
    if sample_rec and wfield in sample_rec:
        orig_val = sample_rec[wfield]
    # Attempt write
    wr = client.write(model, sample_rec['id'], {wfield: wval})
    if wr["ok"]:
        # Restore original value
        if orig_val is not None:
            client.write(model, sample_rec['id'], {wfield: orig_val})
        return True
    return False

# Helper to test create/delete
def test_create_delete(model, create_vals):
    cr = client.create(model, create_vals)
    if not cr["ok"]:
        return False, False
    rec_id = cr["id"]
    dl = client.unlink(model, rec_id)
    return True, dl["ok"]

print('\n=== RBAC CRUD PERFORMANCE REPORT ===')
for model, cfg in KEY_MODELS.items():
    label = cfg.get('label', model)
    print(f"\nModel: {label} ({model})")
    # READ test
    read_res = client.search_read(model, [], ["id"], limit=1)
    can_read = read_res["ok"] and read_res.get('cnt',0)>0
    print(f"  Read: {'YES' if can_read else 'NO'}")

    # WRITE test (if write field defined and we have a record)
    wfield = cfg.get('wfield')
    wval = cfg.get('wval')
    can_write = False
    if can_read and wfield and wfield != 'auto' and read_res.get('recs'):
        sample = read_res['recs'][0]
        if 'id' in sample:
            can_write = test_write(model, wfield, wval, sample)
    print(f"  Write: {'YES' if can_write else 'NO'}")

    # CREATE/DELETE test (if explicit create dict provided)
    create_cfg = cfg.get('create')
    can_create = can_delete = False
    if isinstance(create_cfg, dict):
        can_create, can_delete = test_create_delete(model, create_cfg)
    elif create_cfg == 'auto':
        # Auto mode is complex; skip detailed test for now
        can_create = can_delete = None
    # Show results
    if can_create is None:
        print("  Create/Delete: SKIPPED (auto mode)")
    else:
        print(f"  Create: {'YES' if can_create else 'NO'}")
        print(f"  Delete: {'YES' if can_delete else 'NO'}")