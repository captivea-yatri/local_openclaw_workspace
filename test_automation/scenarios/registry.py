"""Scenario registry — all 15 unique scenarios as runnable classes."""
from __future__ import annotations

from test_automation.catalog import (
    ALL_SCENARIO_IDS,
    DUPLICATE_BY_ID,
    SCRIPT_BY_ID,
    list_scenarios,
)
from test_automation.scenarios.quality_issue_ask_for_review import (
    SCENARIO_NAME as QIL_REVIEW_SCENARIO,
    QualityIssueAskForReviewScenario,
)
from test_automation.scenarios.script_scenario import make_script_scenario_class
from test_automation.scenarios.so_cancel_old_customer import (
    SCENARIO_NAME,
    SoCancelOldCustomerScenario,
)
from test_automation.scenarios.so_link_project_invoice_color import (
    SCENARIO_NAME as COLOR_SCENARIO,
    SoLinkProjectInvoiceColorScenario,
)

SCENARIOS: dict[str, type] = {
    SCENARIO_NAME: SoCancelOldCustomerScenario,
    COLOR_SCENARIO: SoLinkProjectInvoiceColorScenario,
    QIL_REVIEW_SCENARIO: QualityIssueAskForReviewScenario,
}

for _script_id in SCRIPT_BY_ID:
    SCENARIOS[_script_id] = make_script_scenario_class(_script_id)


def list_scenario_ids() -> tuple[str, ...]:
    return ALL_SCENARIO_IDS


def is_script_scenario(name: str) -> bool:
    return name in SCRIPT_BY_ID


def get_scenario_class(name: str) -> type:
    if name in DUPLICATE_BY_ID:
        dup = DUPLICATE_BY_ID[name]
        raise KeyError(
            f"Scenario {name!r} is a duplicate of {dup.duplicate_of!r}. "
            f"Use {dup.duplicate_of!r} instead."
        )
    if name not in SCENARIOS:
        known = ", ".join(sorted(ALL_SCENARIO_IDS))
        raise KeyError(f"Unknown scenario {name!r}. Known: {known}")
    return SCENARIOS[name]


__all__ = [
    "SCENARIOS",
    "get_scenario_class",
    "is_script_scenario",
    "list_scenario_ids",
    "list_scenarios",
]
