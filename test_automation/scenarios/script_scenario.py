"""Subprocess-backed scenarios — bundled RPC scripts with unified Scenario interface."""
from __future__ import annotations

from dataclasses import dataclass

from test_automation.catalog import get_script_entry
from test_automation.run_script import run_script_subprocess
from test_automation.scenarios.base import ScenarioRunResult, StepOutcome
from test_automation.script_matrix.config import ScriptMatrixConfig, get_script_matrix_config


@dataclass
class MatrixRunContext:
    url: str
    db: str
    protocol: str
    admin_user: str
    admin_password: str
    test_login: str
    test_password: str
    role: dict | None = None
    quiet: bool = False
    script_extra: tuple[str, ...] = ()


def _build_extra_args(
    role: dict | None,
    matrix_cfg: ScriptMatrixConfig,
    script_extra: tuple[str, ...] = (),
) -> list[str]:
    extra: list[str] = list(matrix_cfg.extra_args)
    extra.extend(script_extra)
    if matrix_cfg.per_role_args and role:
        extra.extend(matrix_cfg.per_role_args(role))
    return extra


class ScriptSubprocessScenario:
    """Runs a catalogued bundled_scripts/*.py entry via subprocess."""

    SCENARIO_ID: str = ""

    def __init__(self, no_cleanup: bool = False, **_kwargs):
        self.no_cleanup = no_cleanup
        self._ctx: MatrixRunContext | None = None

    @property
    def scenario_name(self) -> str:
        return self.SCENARIO_ID

    def set_matrix_context(self, ctx: MatrixRunContext) -> None:
        self._ctx = ctx

    def bind_admin(self, _admin) -> None:
        pass

    def cleanup_as_admin(self, _admin) -> None:
        pass

    def run(self, _rpc, role_name: str) -> ScenarioRunResult:
        if not self.SCENARIO_ID:
            raise ValueError("SCENARIO_ID not set on ScriptSubprocessScenario subclass")
        if self._ctx is None:
            raise RuntimeError("Call set_matrix_context() before run()")

        entry = get_script_entry(self.SCENARIO_ID)
        matrix_cfg = get_script_matrix_config(self.SCENARIO_ID)
        ctx = self._ctx

        if matrix_cfg.auth_user == "admin":
            rpc_user, rpc_password = ctx.admin_user, ctx.admin_password
        else:
            # Default: feature_matrix_tester with the role assigned for this matrix row
            rpc_user, rpc_password = ctx.test_login, ctx.test_password

        extra = _build_extra_args(ctx.role, matrix_cfg, ctx.script_extra)

        try:
            proc = run_script_subprocess(
                entry,
                url=ctx.url,
                db=ctx.db,
                user=rpc_user,
                password=rpc_password,
                protocol=ctx.protocol,
                no_cleanup=self.no_cleanup,
                extra_args=extra,
                quiet=ctx.quiet,
            )
            success = proc.success
            error = proc.tail() if not success else None
        except Exception as exc:
            success = False
            error = str(exc)

        return ScenarioRunResult(
            scenario=self.SCENARIO_ID,
            role_name=role_name,
            success=success,
            failed_step=None if success else "script",
            error=error,
            steps=[StepOutcome(step="script", ok=success, error=error)],
        )


def make_script_scenario_class(scenario_id: str) -> type[ScriptSubprocessScenario]:
    """Factory: one Scenario class per bundled script id."""

    class _ScriptScenario(ScriptSubprocessScenario):
        SCENARIO_ID = scenario_id

    _ScriptScenario.__name__ = f"{scenario_id}_script"
    _ScriptScenario.__qualname__ = _ScriptScenario.__name__
    return _ScriptScenario
