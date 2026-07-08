"""Ensure QA test user has hr.employee (required for Customer Lost quality logs)."""
from __future__ import annotations

from typing import Callable

from cap_qa_platform.rpc.client import OdooRPCClient


def ensure_tester_employee(
    admin: OdooRPCClient,
    user_id: int,
    company_id: int,
    track: Callable[[str, int], None] | None = None,
) -> int:
    """Link hr.employee to test user if missing; return employee id."""
    existing = admin.search(
        "hr.employee",
        [("user_id", "=", user_id), ("company_id", "=", company_id)],
        limit=1,
    )
    if existing:
        return existing[0]
    user = admin.read("res.users", [user_id], ["name"])[0]
    employee_id = admin.create(
        "hr.employee",
        {
            "name": user.get("name") or "CAP QA Tester",
            "user_id": user_id,
            "company_id": company_id,
        },
    )
    if track:
        track("hr.employee", employee_id)
    return employee_id
