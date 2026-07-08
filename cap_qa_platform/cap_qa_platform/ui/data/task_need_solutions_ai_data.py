"""Data helpers for task Need & Solutions AI UI flow."""
from __future__ import annotations

from dataclasses import dataclass

from cap_qa_platform.rpc.client import OdooRPCClient, m2o_id
from cap_qa_platform.ui.data.generate_task_test_ai_data import (
    load_existing_task_data,
    parse_task_id_from_url,
)

REQUIRED_MODULE = "connect_mistral_ai"

DEFAULT_TRANSCRIPT = """
Meeting transcript (Jordan Momper & Yatri Modi):

Jordan: Working on software to automatically test tasks in Odoo. Can provide an Excel
file with about 10 tests — e.g. create a sale order, add a product, add a customer,
confirm it. The goal is for the software to run tests in Odoo by real clicks, not
XML-RPC calls.

Yatri: cap_qa_platform can help — Playwright UI flows with optional RPC for setup.
OpenRouter offers free models and API keys; free models are enough for reading HTML.

Jordan: Good to know for open source. Only reading HTML — free models should work.

Yatri: Search OpenRouter for free models (e.g. GPT OSS). Can help integrate further.

Jordan: Software will be useful for other cases too. Will reach out if needed.
""".strip()

DEFAULT_PROMPT = (
    "Understand the transcript and generate the Need and Solution for this task. "
    "Write the generated content in the task Description field."
)


@dataclass
class TaskNeedSolutionsUiData:
    project_id: int
    task_id: int
    task_name: str
    task_url: str | None
    transcript: str
    prompt: str


def build_user_message(transcript: str, prompt: str) -> str:
    return f"Call transcript:\n{transcript}\n\nPrompt:\n{prompt}"


def load_task_need_solutions_data(
    admin: OdooRPCClient,
    *,
    task_id: int | None = None,
    task_url: str | None = None,
    transcript: str | None = None,
    prompt: str | None = None,
) -> TaskNeedSolutionsUiData:
    if task_id is None and task_url:
        task_id = parse_task_id_from_url(task_url)
    if not task_id:
        raise ValueError("task_id or task_url with a task id is required.")

    rows = admin.search_read(
        "ir.module.module",
        [("name", "=", REQUIRED_MODULE)],
        ["state"],
        limit=1,
    )
    if not rows or rows[0].get("state") != "installed":
        raise RuntimeError(f"Module {REQUIRED_MODULE!r} is not installed.")

    base = load_existing_task_data(admin, task_id=task_id, task_url=task_url)
    return TaskNeedSolutionsUiData(
        project_id=base.project_id,
        task_id=base.task_id,
        task_name=base.task_name,
        task_url=base.task_url,
        transcript=transcript or DEFAULT_TRANSCRIPT,
        prompt=prompt or DEFAULT_PROMPT,
    )


def read_description_plain(admin: OdooRPCClient, task_id: int) -> str:
    desc = admin.read("project.task", [task_id], ["description"])[0].get("description") or ""
    return desc.strip()
