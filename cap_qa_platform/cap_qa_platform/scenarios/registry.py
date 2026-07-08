"""Scenario registry."""
from __future__ import annotations

from cap_qa_platform.scenarios.so_project_color_overdue_due_date import SoProjectColorOverdueDueDateScenario
from cap_qa_platform.scenarios.ocean_lead_enrichment import OceanLeadEnrichmentScenario
from cap_qa_platform.scenarios.generate_task_test_ai import GenerateTaskTestAiScenario
from cap_qa_platform.scenarios.quality_issue_ask_for_review import QualityIssueAskForReviewScenario
from cap_qa_platform.scenarios.so_cancel_old_customer import SoCancelOldCustomerScenario
from cap_qa_platform.scenarios.so_link_project_invoice_color import SoLinkProjectInvoiceColorScenario

SCENARIO_CLASSES: dict[str, type] = {
    "so_project_color_overdue_due_date": SoProjectColorOverdueDueDateScenario,

    "ocean_lead_enrichment": OceanLeadEnrichmentScenario,

    "generate_task_test_ai": GenerateTaskTestAiScenario,
    "so_cancel_old_customer": SoCancelOldCustomerScenario,
    "so_link_project_invoice_color": SoLinkProjectInvoiceColorScenario,
    "quality_issue_ask_for_review": QualityIssueAskForReviewScenario,
}


def get_scenario_class(scenario_id: str) -> type:
    if scenario_id not in SCENARIO_CLASSES:
        raise KeyError(f"No native scenario class for {scenario_id!r}")
    return SCENARIO_CLASSES[scenario_id]
