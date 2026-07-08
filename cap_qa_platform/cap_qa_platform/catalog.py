"""
Scenario catalog for cap_qa_platform — all custom module QA workflows.

Scripts resolve to module RPC tests or read-only legacy bundled_scripts paths.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cap_qa_platform.paths import ADDONS_ROOT, LEGACY_BUNDLED_SCRIPTS

ScenarioKind = Literal["role_matrix", "script"]
LayerKind = Literal["backend", "ui", "both"]


@dataclass(frozen=True)
class ScenarioEntry:
    id: str
    kind: ScenarioKind
    description: str
    modules: tuple[str, ...]
    use_case: str = ""
    layers: tuple[LayerKind, ...] = ("backend",)
    script_relpath: str | None = None
    protocol_flag: str = "protocol"
    extra_args: tuple[str, ...] = ()
    auth_user: Literal["admin", "tester"] = "tester"

    def resolved_script(self) -> Path | None:
        if not self.script_relpath:
            return None
        candidates = [
            ADDONS_ROOT / self.script_relpath,
            LEGACY_BUNDLED_SCRIPTS / Path(self.script_relpath).name,
        ]
        for path in candidates:
            if path.is_file():
                return path
        return candidates[0]


ROLE_MATRIX_ENTRIES: tuple[ScenarioEntry, ...] = (
    ScenarioEntry(
        id="so_cancel_old_customer",
        kind="role_matrix",
        description="Confirm SO, link project, cancel → partner old_customer",
        modules=(
            "cap_partner",
            "cap_offer",
            "ksc_sale_project_extended",
            "cap_quality_issue_log",
            "access_rights_management",
            "base_user_role",
        ),
        use_case="Per-role SO cancel lifecycle and quality log checks.",
        layers=("backend", "ui"),
    ),
    ScenarioEntry(
        id="so_link_project_invoice_color",
        kind="role_matrix",
        description="SO + project link → invoice due date drives project color",
        modules=(
            "ksc_sale_project_extended",
            "ksc_project_extended",
            "cap_offer",
            "access_rights_management",
        ),
        use_case="Project color rules after link_so_project and invoicing.",
        layers=("backend",),
    ),
    ScenarioEntry(
        id="so_project_color_overdue_due_date",
        kind="role_matrix",
        description="SO + link project → invoice due 3 days ago → orange project color",
        modules=(
            "ksc_project_extended",
            "ksc_sale_project_extended",
            "cap_offer",
            "sale",
        ),
        use_case="ksc_project_extended grace-period orange when invoice due date is 3 days past.",
        layers=("backend",),
    ),
    ScenarioEntry(
        id="quality_issue_ask_for_review",
        kind="role_matrix",
        description="Employee Ask For Review → manager To-Do on quality.issue.log",
        modules=("cap_quality_issue_log", "access_rights_management", "hr"),
        use_case="QIL ask_for_review per role.",
        layers=("backend",),
    ),
    ScenarioEntry(
        id="ocean_lead_enrichment",
        kind="role_matrix",
        description="Ocean.io prospect search → CRM lead import → optional people lookup enrich",
        modules=("cap_ocean_connector", "crm"),
        use_case="Prospect wizard imports Ocean data to crm.lead; live search also runs people enrichment lookup.",
        layers=("backend",),
    ),
    ScenarioEntry(
        id="generate_task_test_ai",
        kind="role_matrix",
        description="Generate Task Test - AI wizard → add task tests on project.task",
        modules=("cap_project_ai", "cap_project_test", "connect_mistral_ai", "project"),
        use_case="Task form → Generate Task Test - AI → wizard Add/Add All → Task Tests tab.",
        layers=("backend", "ui"),
    ),
    ScenarioEntry(
        id="task_need_solutions_ai",
        kind="role_matrix",
        description="AI Assistant → Need & Solution from transcript → task Description",
        modules=("connect_mistral_ai", "project", "ai"),
        use_case="Task form → AI Assistant → transcript + prompt → Let's do it! → Description.",
        layers=("ui",),
    ),
)

SCRIPT_ENTRIES: tuple[ScenarioEntry, ...] = (
    ScenarioEntry(
        id="quality_issue_approval",
        kind="script",
        description="Quality issue + approval.request workflow",
        modules=("cap_quality_issue_log", "approvals"),
        script_relpath="cap_quality_issue_log/scripts/test_quality_issue_approval_rpc.py",
        protocol_flag="rpc",
        layers=("backend",),
    ),
    ScenarioEntry(
        id="inter_company_transaction",
        kind="script",
        description="Inter-company invoice / journal workflow",
        modules=("cap_account_intern_company_transection",),
        script_relpath="inter_company_transaction.py",
        layers=("backend",),
    ),
    ScenarioEntry(
        id="hr_gamification_workflow",
        kind="script",
        description="HR gamification challenges, badges, PTO",
        modules=("cap_gamification", "hr_gamification"),
        script_relpath="hr_gamification_workflow.py",
        extra_args=("--skip-studio",),
        layers=("backend",),
    ),
    ScenarioEntry(
        id="cap_hr_skill",
        kind="script",
        description="HR skill validation workflow",
        modules=("cap_hr_skill",),
        script_relpath="cap_hr_skill/scripts/test_cap_hr_skill_rpc.py",
        layers=("backend",),
    ),
    ScenarioEntry(
        id="cap_single_employee_multi_company",
        kind="script",
        description="Single employee across multi-company",
        modules=("cap_single_employee_for_multi_company",),
        script_relpath="cap_single_employee_multi_company.py",
        layers=("backend",),
    ),
    ScenarioEntry(
        id="ksc_auto_invoice",
        kind="script",
        description="Auto-invoicing on sale orders",
        modules=("ksc_auto_invoice",),
        script_relpath="ksc_auto_invoice.py",
        layers=("backend",),
    ),
    ScenarioEntry(
        id="ksc_product_account_restriction",
        kind="script",
        description="Product/GL restrictions by partner on SO",
        modules=("ksc_product_and_account_restriction_by_partner",),
        script_relpath="ksc_product_account_restriction.py",
        layers=("backend",),
    ),
    ScenarioEntry(
        id="cap_marketing_language_documents",
        kind="script",
        description="CRM marketing language documents",
        modules=("cap_marketing_crm_automation",),
        script_relpath="cap_marketing_language_documents.py",
        layers=("backend",),
    ),
    ScenarioEntry(
        id="cap_software",
        kind="script",
        description="Software license tracking",
        modules=("cap_software",),
        script_relpath="cap_software.py",
        layers=("backend",),
    ),
    ScenarioEntry(
        id="connect_openrouter_ai",
        kind="script",
        description="OpenRouter AI connector smoke",
        modules=("connect_openrouter_ai",),
        script_relpath="connect_openrouter_ai.py",
        layers=("backend",),
    ),
    ScenarioEntry(
        id="connect_mistral_ai",
        kind="script",
        description="Mistral AI connector smoke",
        modules=("connect_mistral_ai", "ai", "ai_app"),
        script_relpath="connect_mistral_ai.py",
        auth_user="admin",
        layers=("backend",),
    ),
ScenarioEntry(
    id="connect_deepseek_ai",
    kind="script",
    description="DeepSeek AI Connector (auto-generated smoke)",
    modules=('connect_deepseek_ai', 'ai', 'ai_app'),
    script_relpath="connect_deepseek_ai/models/test_connect_deepseek_ai_rpc.py",
    auth_user="admin",
    layers=("backend",),
),
)

ROLE_MATRIX_BY_ID = {e.id: e for e in ROLE_MATRIX_ENTRIES}
SCRIPT_BY_ID = {e.id: e for e in SCRIPT_ENTRIES}
ALL_BY_ID = {**ROLE_MATRIX_BY_ID, **SCRIPT_BY_ID}
ALL_SCENARIO_IDS: tuple[str, ...] = tuple(ALL_BY_ID.keys())


def get_entry(scenario_id: str) -> ScenarioEntry:
    if scenario_id not in ALL_BY_ID:
        raise KeyError(f"Unknown scenario {scenario_id!r}. Known: {', '.join(ALL_SCENARIO_IDS)}")
    return ALL_BY_ID[scenario_id]


def list_scenarios(*, layer: LayerKind | None = None) -> list[dict]:
    rows = []
    for entry in ALL_SCENARIO_IDS:
        e = ALL_BY_ID[entry]
        if layer and layer not in e.layers:
            continue
        rows.append(
            {
                "id": e.id,
                "kind": e.kind,
                "description": e.description,
                "modules": list(e.modules),
                "layers": list(e.layers),
                "use_case": e.use_case,
            }
        )
    return rows
