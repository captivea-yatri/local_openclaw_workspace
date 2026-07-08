"""
Central catalog of all RPC test scenarios.

Native flows: test_automation/scenarios/<name>.py
Bundled scripts: test_automation/bundled_scripts/<name>.py (portable copies)
All scenarios are registered in scenarios/registry.py and run via run_matrix.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from test_automation.paths import ADDONS_ROOT, BUNDLED_SCRIPTS, PACKAGE_ROOT

ScenarioKind = Literal["role_matrix", "script", "duplicate"]


@dataclass(frozen=True)
class ScenarioEntry:
    id: str
    kind: ScenarioKind
    description: str
    modules: tuple[str, ...]
    use_case: str = ""
    script_path: Path | None = None
    duplicate_of: str | None = None
    protocol_flag: str = "protocol"  # CLI flag name: protocol | rpc
    extra_args: tuple[str, ...] = ()

    def resolved_script(self) -> Path | None:
        if self.kind == "duplicate" or self.script_path is None:
            return None
        bundled = BUNDLED_SCRIPTS / self.script_path.name
        if bundled.is_file():
            return bundled
        legacy = ADDONS_ROOT / self.script_path
        if legacy.is_file():
            return legacy
        return bundled


# ---------------------------------------------------------------------------
# Role-matrix scenarios (implemented in test_automation/scenarios/)
# ---------------------------------------------------------------------------
ROLE_MATRIX_ENTRIES: tuple[ScenarioEntry, ...] = (
    ScenarioEntry(
        id="so_cancel_old_customer",
        kind="role_matrix",
        description="Confirm SO, link project, cancel SO → partner becomes old_customer",
        modules=(
            "cap_partner",
            "cap_offer",
            "ksc_sale_project_extended",
            "cap_quality_issue_log",
            "access_rights_management",
            "base_user_role",
        ),
        use_case=(
            "Per-role sales/project access: create SO, confirm, link project, cancel, "
            "assert partner status and quality logs. Expectations in expectations/so_cancel_old_customer.json."
        ),
    ),
    ScenarioEntry(
        id="so_link_project_invoice_color",
        kind="role_matrix",
        description="SO + project link → invoice due date drives project color (orange/green)",
        modules=(
            "ksc_sale_project_extended",
            "ksc_project_extended",
            "cap_offer",
            "access_rights_management",
            "base_user_role",
        ),
        use_case=(
            "Per-role access to SO/project/invoicing color rules after link_so_project. "
            "Expectations in expectations/so_link_project_invoice_color.json."
        ),
    ),
    ScenarioEntry(
        id="quality_issue_ask_for_review",
        kind="role_matrix",
        description="Employee Ask For Review → manager To-Do on quality.issue.log",
        modules=("cap_quality_issue_log", "access_rights_management", "hr"),
        use_case=(
            "Per-role QIL workflow: employee asks for review, manager gets To-Do (not approval.request). "
            "Expectations in expectations/quality_issue_ask_for_review.json."
        ),
    ),
)

ROLE_MATRIX_SCENARIO_IDS: tuple[str, ...] = tuple(e.id for e in ROLE_MATRIX_ENTRIES)
ROLE_MATRIX_BY_ID: dict[str, ScenarioEntry] = {e.id: e for e in ROLE_MATRIX_ENTRIES}

# ---------------------------------------------------------------------------
# Standalone scripts (unique workflows only)
# ---------------------------------------------------------------------------
SCRIPT_ENTRIES: tuple[ScenarioEntry, ...] = (
    ScenarioEntry(
        id="quality_issue_approval",
        kind="script",
        description="Quality issue log + approval.request workflow (confirm, approve, stale activity)",
        modules=("cap_quality_issue_log", "approvals"),
        use_case="Full approval.request path (confirm → approve/reject) vs ask_for_review matrix scenario.",
        script_path=Path("quality_issue_approval.py"),
        protocol_flag="rpc",
    ),
    ScenarioEntry(
        id="inter_company_transaction",
        kind="script",
        description="Inter-company invoice / journal entry workflow",
        modules=("cap_account_intern_company_transection",),
        use_case="Inter-company billing and journal mirroring between companies.",
        script_path=Path("inter_company_transaction.py"),
        protocol_flag="protocol",
    ),
    ScenarioEntry(
        id="hr_gamification_workflow",
        kind="script",
        description="Full HR gamification workflow (challenges, pro-rata, PTO, manager quotas, badges)",
        modules=("cap_gamification", "cap_partner", "cap_quality_issue_log", "hr_gamification"),
        use_case="End-to-end gamification: challenges, badges, manager quotas, PTO integration.",
        script_path=Path("hr_gamification_workflow.py"),
        protocol_flag="protocol",
        extra_args=("--skip-studio",),
    ),
    ScenarioEntry(
        id="cap_hr_skill",
        kind="script",
        description="HR skill validation request workflow (employee + validator)",
        modules=("cap_hr_skill",),
        use_case="Skill validation request lifecycle (employee submits, validator approves).",
        script_path=Path("cap_hr_skill.py"),
        protocol_flag="protocol",
    ),
    ScenarioEntry(
        id="cap_single_employee_multi_company",
        kind="script",
        description="Single employee record across multi-company (timesheets, leave, expenses)",
        modules=("cap_single_employee_for_multi_company",),
        use_case="One employee linked to multiple companies: timesheets, leave, expenses RPC checks.",
        script_path=Path("cap_single_employee_multi_company.py"),
        protocol_flag="protocol",
    ),
    ScenarioEntry(
        id="ksc_auto_invoice",
        kind="script",
        description="Automatic invoicing fields and timesheet invoice methods on sale.order",
        modules=("ksc_auto_invoice",),
        use_case="Auto-invoice fields and timesheet-based invoicing on sale orders.",
        script_path=Path("ksc_auto_invoice.py"),
        protocol_flag="protocol",
    ),
    ScenarioEntry(
        id="ksc_product_account_restriction",
        kind="script",
        description="Product and GL account restrictions by partner on sale orders",
        modules=("ksc_product_and_account_restriction_by_partner",),
        use_case="Partner-specific product and account restrictions on SO lines.",
        script_path=Path("ksc_product_account_restriction.py"),
        protocol_flag="protocol",
    ),
    ScenarioEntry(
        id="cap_marketing_language_documents",
        kind="script",
        description="CRM marketing language and document automation",
        modules=("cap_marketing_crm_automation",),
        use_case="CRM lead language detection and marketing document generation.",
        script_path=Path("cap_marketing_language_documents.py"),
        protocol_flag="protocol",
    ),
    ScenarioEntry(
        id="cap_software",
        kind="script",
        description="Software product / license tracking RPC checks",
        modules=("cap_software",),
        use_case="Software license and product tracking workflows.",
        script_path=Path("cap_software.py"),
        protocol_flag="protocol",
    ),
    ScenarioEntry(
        id="connect_openrouter_ai",
        kind="script",
        description="OpenRouter AI connector RPC and optional live AI scenarios",
        modules=("connect_openrouter_ai",),
        use_case="OpenRouter connector smoke + optional --live API calls per role.",
        script_path=Path("connect_openrouter_ai.py"),
        protocol_flag="protocol",
    ),
    ScenarioEntry(
        id="connect_mistral_ai",
        kind="script",
        description="Native Mistral AI connector — structural smoke + optional live API (--live)",
        modules=("connect_mistral_ai", "ai", "ai_app"),
        use_case=(
            "Mistral connector smoke/live tests. Matrix runs RPC as admin; use run_matrix.py "
            "--live --agent-id --mistral-key for full role matrix."
        ),
        script_path=Path("connect_mistral_ai.py"),
        protocol_flag="protocol",
    ),
)

# ---------------------------------------------------------------------------
# Duplicates — documented aliases, not run separately
# ---------------------------------------------------------------------------
DUPLICATE_ENTRIES: tuple[ScenarioEntry, ...] = (
    ScenarioEntry(
        id="so_cancel_old_customer_status_rpc",
        kind="duplicate",
        description="Legacy standalone SO cancel script",
        modules=("cap_partner", "ksc_sale_project_extended"),
        script_path=Path("cap_partner/scripts/test_so_cancel_old_customer_status_rpc.py"),
        duplicate_of="so_cancel_old_customer",
    ),
    ScenarioEntry(
        id="cap_gamification_rpc",
        kind="duplicate",
        description="Subset gamification test; use hr_gamification_workflow for full coverage",
        modules=("cap_gamification",),
        script_path=Path("cap_gamification/scripts/test_cap_gamification_rpc.py"),
        duplicate_of="hr_gamification_workflow",
    ),
    ScenarioEntry(
        id="quality_issue_approval_workflow",
        kind="duplicate",
        description="Odoo shell version of quality_issue_approval RPC test",
        modules=("cap_quality_issue_log", "approvals"),
        script_path=Path(
            "cap_quality_issue_log/scripts/test_quality_issue_approval_workflow.py"
        ),
        duplicate_of="quality_issue_approval",
    ),
    ScenarioEntry(
        id="inter_company_manual",
        kind="duplicate",
        description="Odoo shell manual runner; use inter_company_transaction RPC test",
        modules=("cap_account_intern_company_transection",),
        script_path=Path(
            "cap_account_intern_company_transection/scripts/test_inter_company_manual.py"
        ),
        duplicate_of="inter_company_transaction",
    ),
)

SCRIPT_BY_ID: dict[str, ScenarioEntry] = {e.id: e for e in SCRIPT_ENTRIES}
DUPLICATE_BY_ID: dict[str, ScenarioEntry] = {e.id: e for e in DUPLICATE_ENTRIES}

ALL_SCENARIO_IDS: tuple[str, ...] = (
    ROLE_MATRIX_SCENARIO_IDS + tuple(e.id for e in SCRIPT_ENTRIES)
)


def get_script_entry(scenario_id: str) -> ScenarioEntry:
    if scenario_id in DUPLICATE_BY_ID:
        dup = DUPLICATE_BY_ID[scenario_id]
        raise KeyError(
            f"Scenario {scenario_id!r} is a duplicate of {dup.duplicate_of!r}. "
            f"Use: {dup.duplicate_of}"
        )
    if scenario_id in SCRIPT_BY_ID:
        return SCRIPT_BY_ID[scenario_id]
    if scenario_id in ROLE_MATRIX_SCENARIO_IDS:
        raise KeyError(
            f"Scenario {scenario_id!r} is a role-matrix scenario. "
            "Use run_feature_matrix.py or run_test_suite.py with --kind role_matrix."
        )
    known = ", ".join(sorted(ALL_SCENARIO_IDS))
    raise KeyError(f"Unknown scenario {scenario_id!r}. Known: {known}")


def list_scenarios() -> list[dict]:
    rows: list[dict] = []
    for entry in ROLE_MATRIX_ENTRIES:
        rows.append(_scenario_row(entry, path=f"test_automation/scenarios/{entry.id}.py"))
    for entry in SCRIPT_ENTRIES:
        rows.append(
            _scenario_row(
                entry,
                path=f"test_automation/bundled_scripts/{entry.script_path.name}"
                if entry.script_path
                else None,
            )
        )
    for entry in DUPLICATE_ENTRIES:
        rows.append(
            _scenario_row(
                entry,
                path=str(entry.script_path) if entry.script_path else None,
            )
        )
    return rows


def _scenario_row(entry: ScenarioEntry, *, path: str | None) -> dict:
    return {
        "id": entry.id,
        "kind": entry.kind,
        "description": entry.description,
        "use_case": entry.use_case,
        "modules": list(entry.modules),
        "duplicate_of": entry.duplicate_of,
        "path": path,
    }


def _rpc_auth_label(scenario_id: str, kind: str) -> str:
    if kind == "role_matrix":
        return "feature_matrix_tester (per role)"
    from test_automation.script_matrix.config import get_script_matrix_config

    cfg = get_script_matrix_config(scenario_id)
    if cfg.auth_user == "admin":
        return "admin (--user); role assigned to tester for audit"
    return "feature_matrix_tester (per role)"


AUTOMATION_USE_CASES: tuple[str, ...] = (
    "Smoke-test all custom RPC workflows once before deploy or after module upgrade.",
    "Role-based access: run each scenario as feature_matrix_tester with one res.users.role at a time.",
    "Compare results to expectations JSON → PASS / FAIL / BLOCKED_OK / REPORT verdicts.",
    "Unified matrix: any scenario × all roles (access_rights_management roles from DB or XML).",
    "Self-contained package: scenarios, bundled scripts, runners — copy test_automation/ to migrate.",
    "CI: --strict + --report-file for gatekeeping once expectations are filled.",
)

RUN_MODES: tuple[tuple[str, str], ...] = (
    (
        "smoke",
        "Each scenario once (default role: Team Manager on feature_matrix_tester). Fast sanity check.",
    ),
    (
        "role",
        "3 business role-matrix scenarios × all roles. Native RPC per role.",
    ),
    (
        "role-scripts",
        "11 bundled script scenarios × all roles.",
    ),
    (
        "full",
        "role + role-scripts — complete matrix (14 scenarios × N roles).",
    ),
)

ENTRY_POINTS: tuple[tuple[str, str], ...] = (
    ("run_test_suite.py", "Main entry: --list, --all, --mode smoke|role|role-scripts|full"),
    ("run_matrix.py", "Unified matrix: --scenario, --all, --live, --agent-id, --mistral-key"),
    ("run_feature_matrix.py", "Single business scenario × roles"),
    ("run_role_matrix.py", "All 3 business scenarios × roles"),
    ("run_script_matrix.py", "All 11 scripts × roles"),
)


def format_catalog_list() -> str:
    """Full human-readable catalog for --list (scenarios + automation use cases)."""
    lines: list[str] = []
    w = lines.append

    w("Odoo RPC test automation — catalog")
    w("=" * 72)
    w("")
    w("AUTOMATION USE CASES")
    w("-" * 72)
    for i, uc in enumerate(AUTOMATION_USE_CASES, 1):
        w(f"  {i}. {uc}")
    w("")
    w("ENTRY POINTS")
    w("-" * 72)
    for name, desc in ENTRY_POINTS:
        w(f"  {name:<22} {desc}")
    w("")
    w("RUN MODES (run_test_suite.py --mode …)")
    w("-" * 72)
    for mode, desc in RUN_MODES:
        w(f"  {mode:<14} {desc}")
    w("")
    w("ROLES")
    w("-" * 72)
    w("  --roles-from db   All res.users.role in database (default on matrix/suite)")
    w("  --roles-from xml  Roles from access_rights_management/data/roles_data.xml")
    w("  --roles NAME …    Subset only (e.g. --roles President \"Team Manager\")")
    w("")
    w("TEST USER")
    w("-" * 72)
    w("  feature_matrix_tester / feature_matrix_test")
    w("  Admin (--user) assigns roles, creates fallback data, cleans up.")
    w("")
    w(f"SCENARIOS ({len(ALL_SCENARIO_IDS)} unique: {len(ROLE_MATRIX_ENTRIES)} role_matrix + {len(SCRIPT_ENTRIES)} script)")
    w("=" * 72)

    for entry in (*ROLE_MATRIX_ENTRIES, *SCRIPT_ENTRIES):
        w("")
        w(f"  [{entry.kind}] {entry.id}")
        w(f"    Description : {entry.description}")
        if entry.use_case:
            w(f"    Use case    : {entry.use_case}")
        w(f"    Modules     : {', '.join(entry.modules) or '—'}")
        w(f"    RPC as      : {_rpc_auth_label(entry.id, entry.kind)}")
        w(f"    Per-role    : yes (matrix / --mode role|role-scripts|full)")
        if entry.kind == "role_matrix":
            w(f"    Path        : test_automation/scenarios/{entry.id}.py")
            w(f"    Expectations: test_automation/expectations/{entry.id}.json")
        else:
            w(f"    Path        : test_automation/bundled_scripts/{entry.script_path.name}")
            w(f"    Expectations: test_automation/expectations/scripts/{entry.id}.json")

    w("")
    w("DUPLICATES (aliases — do not run; use canonical id)")
    w("-" * 72)
    for entry in DUPLICATE_ENTRIES:
        w(f"  {entry.id}")
        w(f"    → use {entry.duplicate_of!r} — {entry.description}")

    w("")
    w("DOCS")
    w("-" * 72)
    w("  STAGING_QA.md   Run tiers, CI, triage, expectations workflow")
    w("  ADD_SCENARIO.md  How teammates attach a new feature")
    w("  PR_CHECKLIST.md  PR checklist for test_automation changes")
    w("")
    w("EXAMPLE COMMANDS")
    w("-" * 72)
    w("  ./test_automation/run_staging_smoke.sh")
    w("  python3 test_automation/run_test_suite.py --list")
    w("  python3 test_automation/run_test_suite.py --all --mode smoke \\")
    w("      --load-staging-env")
    w("  python3 test_automation/run_test_suite.py --all --mode role --roles-from db \\")
    w("      --url ... --db ... --user admin1 --password 'a'")
    w("  python3 test_automation/run_matrix.py --scenario connect_mistral_ai \\")
    w("      --roles-from db --live --agent-id 2 --url ... --db ... --user admin1 --password 'a'")
    w("")
    return "\n".join(lines)
