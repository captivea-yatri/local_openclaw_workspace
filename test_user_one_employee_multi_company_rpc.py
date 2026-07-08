#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test that a single Odoo user can be linked to **only one** employee, but that employee can operate
in multiple companies (via the user's allowed companies).

The test performs:
1. Create two companies (TestCo A & TestCo B).
2. Create a clean test user and grant it access to both companies (field ``allowed_company_ids``).
3. Create ONE employee linked to that user (primary company = A).
4. Verify that a second employee for the same user is rejected.
5. Verify the employee can submit a leave request in Company B (different from the primary company) – this proves the employee works across the allowed companies.
"""
from __future__ import annotations

import argparse
import json
import sys
import xmlrpc.client
from typing import Any

# ---------------------------------------------------------------------------
# Configuration (override via CLI args)
# ---------------------------------------------------------------------------
DEFAULT_URL = "https://uriah-apolitical-masako.ngrok-free.dev"
DEFAULT_DB = "odoo19_captivea2"
DEFAULT_USER = "admin1"
DEFAULT_PASSWORD = "a"

MODEL_RES_USERS = "res.users"
MODEL_RES_COMPANY = "res.company"
MODEL_HR_EMPLOYEE = "hr.employee"
MODEL_HR_LEAVE_TYPE = "hr.leave.type"
MODEL_HR_LEAVE_ALLOCATION = "hr.leave.allocation"
MODEL_HR_LEAVE = "hr.leave"

# ---------------------------------------------------------------------------
# Helper RPC client
# ---------------------------------------------------------------------------
def rpc_client(url: str, db: str, username: str, password: str):
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
    uid = common.authenticate(db, username, password, {})
    if not uid:
        raise RuntimeError("Authentication failed")
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
    return uid, models

# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------
def ensure_company(models, uid, password, db, name: str) -> int:
    existing = models.execute_kw(db, uid, password, MODEL_RES_COMPANY, "search", [[('name', '=', name)]], {'limit': 1})
    if existing:
        return existing[0]
    return models.execute_kw(db, uid, password, MODEL_RES_COMPANY, "create", [{'name': name}])

def cleanup_user(models, uid, password, db, login: str) -> None:
    users = models.execute_kw(db, uid, password, MODEL_RES_USERS, "search", [[('login', '=', login)]], {'limit': 1})
    if not users:
        return
    user_id = users[0]
    # delete any employee linked to this user (any company)
    emp_ids = models.execute_kw(db, uid, password, MODEL_HR_EMPLOYEE, "search", [[('user_id', '=', user_id)]])
    if emp_ids:
        models.execute_kw(db, uid, password, MODEL_HR_EMPLOYEE, "unlink", [emp_ids])
    models.execute_kw(db, uid, password, MODEL_RES_USERS, "unlink", [[user_id]])

def main() -> int:
    parser = argparse.ArgumentParser(description="Test single user → one employee (multi‑company) via RPC")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    args = parser.parse_args()

    uid, models = rpc_client(args.url, args.db, args.user, args.password)
    print(f"Authenticated uid={uid}")

    # ------------------------------------------------------------
    # 1️⃣  Two companies
    # ------------------------------------------------------------
    comp_a = ensure_company(models, uid, args.password, args.db, "TestCo A")
    comp_b = ensure_company(models, uid, args.password, args.db, "TestCo B")
    print(f"Companies: A={comp_a}, B={comp_b}")

    # ------------------------------------------------------------
    # 2️⃣  Clean / create test user with access to both companies
    # ------------------------------------------------------------
    test_login = "single_user_multi_co"
    cleanup_user(models, uid, args.password, args.db, test_login)
    user_id = models.execute_kw(args.db, uid, args.password, MODEL_RES_USERS, "create", [{
        "name": "Single‑User Multi‑Co Test",
        "login": test_login,
        "email": f"{test_login}@example.com",
        # Default company (primary) – pick Company A
        "company_id": comp_a,
        # Allowed companies (many2many) – give access to both A and B
        "company_ids": [(6, 0, [comp_a, comp_b])],
    }])
    print(f"Test user created: id={user_id}")

    # Verify allowed companies on the user
    user_data = models.execute_kw(args.db, uid, args.password, MODEL_RES_USERS, "read", [[user_id], ['company_id', 'company_ids']])
    print("User companies (primary + allowed):", json.dumps(user_data, indent=2))

    # ------------------------------------------------------------
    # 3️⃣  Create ONE employee linked to this user (primary company = A)
    # ------------------------------------------------------------
    employee_id = models.execute_kw(args.db, uid, args.password, MODEL_HR_EMPLOYEE, "create", [{
        "name": "Multi‑Co Employee",
        "company_id": comp_a,
        "user_id": user_id,
    }])
    print(f"Employee created: id={employee_id}")

    # ------------------------------------------------------------
    # 4️⃣  Attempt to create a SECOND employee for the SAME user – should fail
    # ------------------------------------------------------------
    try:
        models.execute_kw(args.db, uid, args.password, MODEL_HR_EMPLOYEE, "create", [{
            "name": "Second Employee",
            "company_id": comp_a,
            "user_id": user_id,
        }])
        print("ERROR: Second employee was created – constraint not enforced!")
    except xmlrpc.client.Fault as e:
        print("Expected failure when creating second employee (constraint works):")
        print(e.faultString)

    # ------------------------------------------------------------
    # 5️⃣  Verify the employee can submit a leave in Company B (allowed via user)
    # ------------------------------------------------------------
    # a) create a leave type in Company B
    leave_type_b = models.execute_kw(args.db, uid, args.password, MODEL_HR_LEAVE_TYPE, "create", [{
        "name": "Test Leave Type B",
        "company_id": comp_b,
        "requires_allocation": "no",
        "employee_requests": "yes",
    }])
    # b) create allocation for the employee in Company B (employee mode)
    alloc_id = models.execute_kw(args.db, uid, args.password, MODEL_HR_LEAVE_ALLOCATION, "create", [{
        "holiday_type": "employee",
        "holiday_status_id": leave_type_b,
        "employee_id": employee_id,
        "company_id": comp_b,
        "number_of_days": 5,
    }])
    # Validate allocation (some modules require explicit validation)
    try:
        models.execute_kw(args.db, uid, args.password, MODEL_HR_LEAVE_ALLOCATION, "action_validate", [[alloc_id]], {})
    except Exception:
        pass
    # c) create the leave request for the employee in Company B
    leave_id = models.execute_kw(args.db, uid, args.password, MODEL_HR_LEAVE, "create", [{
        "employee_id": employee_id,
        "holiday_status_id": leave_type_b,
        "date_from": "2026-07-10",
        "date_to": "2026-07-10",
        "company_id": comp_b,
    }])
    print(f"Leave created in Company B (via same employee): id={leave_id}")

    # ------------------------------------------------------------
    # 6️⃣  Optional cleanup (comment out if you want to inspect data manually)
    # ------------------------------------------------------------
    # models.execute_kw(args.db, uid, args.password, MODEL_HR_LEAVE, "unlink", [[leave_id]])
    # models.execute_kw(args.db, uid, args.password, MODEL_HR_LEAVE_ALLOCATION, "unlink", [[alloc_id]])
    # models.execute_kw(args.db, uid, args.password, MODEL_HR_LEAVE_TYPE, "unlink", [[leave_type_b]])
    # models.execute_kw(args.db, uid, args.password, MODEL_HR_EMPLOYEE, "unlink", [[employee_id]])
    # models.execute_kw(args.db, uid, args.password, MODEL_RES_USERS, "unlink", [[user_id]])

    return 0

if __name__ == "__main__":
    sys.exit(main())
