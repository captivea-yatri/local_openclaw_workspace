"""Per-script matrix configuration (auth user, role assignment, extra CLI args)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

AuthUser = Literal["admin", "tester"]


@dataclass(frozen=True)
class ScriptMatrixConfig:
    """How to run one catalogued script for a single role in the matrix."""

    auth_user: AuthUser = "tester"
    assign_role: bool = True
    extra_args: tuple[str, ...] = ()
    per_role_args: Callable[[dict], list[str]] | None = None


# connect_mistral_ai: run as admin1 (full admin rights) — global key is server-side.
# Role is still assigned to feature_matrix_tester for audit; script uses --user admin.
SCRIPT_MATRIX_CONFIG: dict[str, ScriptMatrixConfig] = {
    "connect_mistral_ai": ScriptMatrixConfig(
        auth_user="admin",
        assign_role=True,
    ),
}


def get_script_matrix_config(scenario_id: str) -> ScriptMatrixConfig:
    return SCRIPT_MATRIX_CONFIG.get(scenario_id, ScriptMatrixConfig())
