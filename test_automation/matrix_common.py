"""Shared verdict classification for feature matrix and script matrix."""
from __future__ import annotations

from test_automation.rpc.errors import is_access_error


def classify_matrix_outcome(
    role_name: str,
    *,
    success: bool,
    failed_step: str | None,
    error: str | None,
    expectations: dict,
    strict: bool,
) -> dict:
    full_access = set(expectations.get("full_access") or [])
    blocked = expectations.get("blocked") or {}
    blocked_spec = blocked.get(role_name)

    verdict = "REPORT"
    detail = ""

    if role_name in full_access:
        if success:
            verdict = "PASS"
            detail = "Full flow completed"
        else:
            verdict = "FAIL"
            detail = f"Expected full access; failed at {failed_step}: {error}"

    elif blocked_spec:
        expected_step = blocked_spec.get("at", "script")
        if not success and (failed_step == expected_step or expected_step == "script"):
            if is_access_error(Exception(error or "")):
                verdict = "BLOCKED_OK"
                detail = f"Blocked at {expected_step} as expected"
            else:
                verdict = "FAIL"
                detail = f"Blocked at {expected_step} but not AccessError: {error}"
        elif success:
            verdict = "FAIL"
            detail = "Expected block but full flow succeeded"
        else:
            verdict = "FAIL"
            detail = (
                f"Expected block at {expected_step}, "
                f"got {failed_step}: {error}"
            )
    else:
        if success:
            detail = "Completed (not in full_access — review expectations)"
        else:
            detail = f"Failed at {failed_step}: {error}"
        if strict and not success:
            verdict = "FAIL"
        elif strict and success and role_name not in full_access:
            verdict = "REPORT"

    return {
        "role": role_name,
        "verdict": verdict,
        "detail": detail,
        "success": success,
        "failed_step": failed_step,
        "error": error,
    }
