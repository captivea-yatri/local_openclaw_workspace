"""RPC test data for generate_task_test_ai UI flow."""
from __future__ import annotations

import re
from dataclasses import dataclass

from cap_qa_platform.rpc.client import OdooRPCClient, m2o_id
from cap_qa_platform.scenarios.generate_task_test_ai import (
    REQUIRED_MODULE,
    GenerateTaskTestAiScenario,
)


@dataclass
class GenerateTaskTestAiUiData:
    project_id: int
    task_id: int
    task_name: str
    task_url: str | None = None


def parse_task_id_from_url(task_url: str) -> int | None:
    match = re.search(r"/(?:action-\d+|tasks?)/(\d+)(?:\?|$|/)", task_url)
    if match:
        return int(match.group(1))
    match = re.search(r"resId=(\d+)", task_url)
    if match:
        return int(match.group(1))
    match = re.search(r"[?&]id=(\d+)", task_url)
    if match:
        return int(match.group(1))
    return None


def load_existing_task_data(
    admin: OdooRPCClient,
    *,
    task_id: int | None = None,
    task_url: str | None = None,
) -> GenerateTaskTestAiUiData:
    if task_id is None and task_url:
        task_id = parse_task_id_from_url(task_url)
    if not task_id:
        raise ValueError("task_id or a URL containing a task id is required.")

    rows = admin.search_read(
        "ir.module.module",
        [("name", "=", REQUIRED_MODULE)],
        ["state"],
        limit=1,
    )
    if not rows or rows[0].get("state") != "installed":
        raise RuntimeError(f"Module {REQUIRED_MODULE!r} is not installed.")

    task = admin.read("project.task", [task_id], ["name", "project_id", "description"])[0]
    if not (task.get("description") or "").strip():
        raise AssertionError("Task description must be set before generating AI task tests.")

    project_id = m2o_id(task["project_id"])
    if not project_id:
        raise AssertionError(f"Task {task_id} has no project_id.")

    return GenerateTaskTestAiUiData(
        project_id=project_id,
        task_id=task_id,
        task_name=task["name"],
        task_url=task_url,
    )


def prepare_generate_task_test_ai_data(
    tester: OdooRPCClient,
    admin: OdooRPCClient,
    *,
    no_cleanup: bool = False,
) -> tuple[GenerateTaskTestAiUiData, GenerateTaskTestAiScenario]:
    scenario = GenerateTaskTestAiScenario(no_cleanup=no_cleanup)
    scenario.bind_admin(admin)
    scenario._assert_module_installed()
    ctx = scenario._setup_task(tester)
    task_name = admin.read("project.task", [ctx["task_id"]], ["name"])[0]["name"]
    return (
        GenerateTaskTestAiUiData(
            project_id=ctx["project_id"],
            task_id=ctx["task_id"],
            task_name=task_name,
            task_url=None,
        ),
        scenario,
    )
