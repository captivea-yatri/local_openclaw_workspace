"""Run UI smoke flows."""
from __future__ import annotations

import json
import sys

from cap_qa_platform.catalog import list_scenarios
from cap_qa_platform.ui.flows.generate_task_test_ai import run_generate_task_test_ai_ui_smoke
from cap_qa_platform.ui.flows.so_cancel_old_customer import run_so_cancel_ui_smoke
from cap_qa_platform.ui.flows.task_need_solutions_ai import run_task_need_solutions_ai_ui_smoke

UI_FLOW_REGISTRY = {
    "generate_task_test_ai": run_generate_task_test_ai_ui_smoke,
    "task_need_solutions_ai": run_task_need_solutions_ai_ui_smoke,
    "so_cancel_old_customer": run_so_cancel_ui_smoke,
}


def run_ui_smoke(
    scenario_id: str, role: str = "President", *, skip_backend: bool = True
) -> int:
    fn = UI_FLOW_REGISTRY.get(scenario_id)
    if fn is None:
        print(
            f"No UI flow for {scenario_id!r}. UI flows: {', '.join(UI_FLOW_REGISTRY)}",
            file=sys.stderr,
        )
        return 2
    result = fn(role=role, skip_backend=skip_backend)
    payload = {
        "scenario": scenario_id,
        "ok": result.ok,
        "detail": result.detail,
        "steps": [{"step": s.step, "ok": s.ok, "error": s.error} for s in result.steps],
        "records": result.records,
    }
    print(json.dumps(payload, indent=2))
    return 0 if result.ok else 1


def list_ui_scenarios() -> list[dict]:
    return [s for s in list_scenarios(layer="ui") if s["id"] in UI_FLOW_REGISTRY]
