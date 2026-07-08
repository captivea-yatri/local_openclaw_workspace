#!/usr/bin/env python3
"""
Odoo Quality Issue Log checker & cleaner

Credentials (replace if they change):
    URL      : https://staging-odoo19-captivea.odoo.com
    DB       : captivea-staging-odoo19-33645016
    USERNAME : divyesh
    PASSWORD : a,

Target record:
    model = quality.issue.log
    id    = 72046
"""

import sys, json, xmlrpc.client
from urllib.parse import urljoin

ODOO_URL = "https://staging-odoo19-captivea.odoo.com"
DB_NAME = "captivea-staging-odoo19-33645016"
USERNAME = "divyesh"
PASSWORD = "a,"

MODEL_NAME = "quality.issue.log"
RECORD_ID = 72046
EXPECTED_STATE = "warning"
METHOD_NAME = "action_check_and_clear"

def exit_error(msg):
    sys.stderr.write(f"ERROR: {msg}\n")
    sys.exit(1)

def get_common_endpoint(suffix):
    return xmlrpc.client.ServerProxy(urljoin(ODOO_URL, f"/xmlrpc/2/{suffix}"))

def login():
    common = get_common_endpoint("common")
    uid = common.authenticate(DB_NAME, USERNAME, PASSWORD, {})
    if not uid:
        exit_error("Authentication failed – check credentials.")
    print(f"[INFO] Logged in as uid={uid}")
    return uid

def read_record(uid, object_proxy):
    fields = ["id", "state"]
    recs = object_proxy.read(DB_NAME, uid, PASSWORD, [RECORD_ID], fields)
    if not recs:
        exit_error(f"Record id={RECORD_ID} not found in model {MODEL_NAME}.")
    return recs[0]

def call_method(uid, object_proxy, method_name):
    return object_proxy.execute_kw(DB_NAME, uid, PASSWORD, MODEL_NAME, method_name, [[RECORD_ID]], {})

def record_exists(uid, object_proxy):
    try:
        object_proxy.read(DB_NAME, uid, PASSWORD, [RECORD_ID], ["id"])
        return True
    except xmlrpc.client.Fault as fault:
        if fault.faultCode == 200:
            return False
        raise

def main():
    uid = login()
    obj = get_common_endpoint("object")
    rec = read_record(uid, obj)
    cur_state = rec.get("state")
    print(f"[INFO] Record {RECORD_ID} current state: '{cur_state}'")
    if cur_state != EXPECTED_STATE:
        print(f"[WARN] Expected state '{EXPECTED_STATE}'. Button not visible. Exiting.")
        sys.exit(0)
    print(f"[INFO] Invoking method '{METHOD_NAME}' on record {RECORD_ID} …")
    result = call_method(uid, obj, METHOD_NAME)
    print("[INFO] Method returned:", json.dumps(result, indent=2))
    exists = record_exists(uid, obj)
    if exists:
        print(f"[RESULT] Record {RECORD_ID} still exists after the call.")
    else:
        print(f"[RESULT] Record {RECORD_ID} has been deleted (expected).")

if __name__ == "__main__":
    main()
