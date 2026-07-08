"""Base types for feature scenarios."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StepOutcome:
    step: str
    ok: bool
    error: str | None = None


@dataclass
class ScenarioRunResult:
    scenario: str
    role_name: str
    success: bool
    failed_step: str | None = None
    error: str | None = None
    steps: list[StepOutcome] = field(default_factory=list)
    records: dict[str, Any] = field(default_factory=dict)
    quality_log_count: int | None = None

    def completed_step(self) -> str | None:
        if self.steps:
            return self.steps[-1].step
        return None
