#!/usr/bin/env python3
"""Refresh bundled_scripts/ from module source RPC test files."""
from __future__ import annotations

import shutil
from pathlib import Path

from test_automation.paths import ADDONS_ROOT, BUNDLED_SCRIPTS

SOURCES: dict[str, str] = {
    "quality_issue_approval.py": "cap_quality_issue_log/scripts/test_quality_issue_approval_rpc.py",
    "inter_company_transaction.py": "cap_account_intern_company_transection/test_inter_company_rpc.py",
    "hr_gamification_workflow.py": "cap_gamification/scripts/test_hr_gamification_workflow_rpc.py",
    "cap_hr_skill.py": "cap_hr_skill/scripts/test_cap_hr_skill_rpc.py",
    "cap_single_employee_multi_company.py": (
        "cap_single_employee_for_multi_company/models/"
        "test_cap_single_employee_for_multi_company_rpc.py"
    ),
    "ksc_auto_invoice.py": "ksc_auto_invoice/models/test_ksc_auto_invoice_rpc.py",
    "ksc_product_account_restriction.py": (
        "ksc_product_and_account_restriction_by_partner/models/"
        "test_product_account_restriction_rpc.py"
    ),
    "cap_marketing_language_documents.py": (
        "cap_marketing_crm_automation/models/test_marketing_language_documents_rpc.py"
    ),
    "cap_software.py": "cap_software/models/test_cap_software_rpc.py",
    "connect_openrouter_ai.py": "connect_openrouter_ai/models/test_connect_openrouter_ai_rpc.py",
    "connect_mistral_ai.py": "connect_mistral_ai/models/test_connect_mistral_ai_rpc.py",
}


def main() -> int:
    BUNDLED_SCRIPTS.mkdir(parents=True, exist_ok=True)
    errors = 0
    for dest_name, src_rel in SOURCES.items():
        src = ADDONS_ROOT / src_rel
        dst = BUNDLED_SCRIPTS / dest_name
        if not src.is_file():
            print(f"MISSING source: {src}")
            errors += 1
            continue
        shutil.copy2(src, dst)
        print(f"copied {dest_name}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
