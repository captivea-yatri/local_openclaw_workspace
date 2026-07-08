"""Run a catalogued standalone RPC test script via subprocess."""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SCRIPT_TIMEOUT = int(os.environ.get("ODOO_SCRIPT_TIMEOUT", "600"))

from test_automation.catalog import ScenarioEntry, get_script_entry
from test_automation.paths import ADDONS_ROOT


@dataclass
class ScriptRunResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    def tail(self, max_chars: int = 400) -> str:
        text = (self.stderr or self.stdout or "").strip()
        if len(text) <= max_chars:
            return text
        return "..." + text[-max_chars:]


def build_script_command(
    entry: ScenarioEntry,
    *,
    url: str,
    db: str,
    user: str,
    password: str,
    protocol: str = "jsonrpc",
    no_cleanup: bool = False,
    extra_args: list[str] | None = None,
) -> list[str]:
    script = entry.resolved_script()
    if script is None or not script.is_file():
        raise FileNotFoundError(f"Script not found: {entry.script_path}")

    cmd = [sys.executable, str(script), "--url", url, "--db", db, "--user", user, "--password", password]
    flag = entry.protocol_flag
    cmd.extend([f"--{flag}", protocol])

    if no_cleanup:
        cmd.append("--no-cleanup")

    cmd.extend(entry.extra_args)

    if extra_args:
        cmd.extend(extra_args)

    return cmd


def run_script_subprocess(
    entry: ScenarioEntry,
    *,
    url: str,
    db: str,
    user: str,
    password: str,
    protocol: str = "jsonrpc",
    no_cleanup: bool = False,
    extra_args: list[str] | None = None,
    quiet: bool = False,
    timeout: int | None = None,
) -> ScriptRunResult:
    cmd = build_script_command(
        entry,
        url=url,
        db=db,
        user=user,
        password=password,
        protocol=protocol,
        no_cleanup=no_cleanup,
        extra_args=extra_args,
    )
    if not quiet:
        print("=" * 80)
        print(f"SCRIPT SCENARIO: {entry.id}")
        print(f"Command     : {' '.join(cmd)}")
        print("=" * 80)
    run_timeout = timeout if timeout is not None else DEFAULT_SCRIPT_TIMEOUT
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(ADDONS_ROOT),
            capture_output=True,
            text=True,
            timeout=run_timeout,
        )
    except subprocess.TimeoutExpired as exc:
        msg = f"Script timed out after {run_timeout}s: {' '.join(cmd)}"
        if not quiet:
            print(msg, file=sys.stderr)
        out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        err = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        err = f"{msg}\n{err}".strip()
        return ScriptRunResult(exit_code=124, stdout=out, stderr=err)
    if not quiet and completed.stdout:
        print(completed.stdout)
    if not quiet and completed.stderr:
        print(completed.stderr, file=sys.stderr)
    return ScriptRunResult(
        exit_code=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def run_script_scenario(
    scenario_id: str,
    *,
    url: str,
    db: str,
    user: str,
    password: str,
    protocol: str = "jsonrpc",
    no_cleanup: bool = False,
    extra_args: list[str] | None = None,
) -> int:
    entry = get_script_entry(scenario_id)
    if entry.kind != "script":
        raise ValueError(f"{scenario_id} is not a script scenario")
    print("=" * 80)
    print(f"SCRIPT SCENARIO: {entry.id}")
    print(f"Description : {entry.description}")
    print(f"Modules     : {', '.join(entry.modules)}")
    result = run_script_subprocess(
        entry,
        url=url,
        db=db,
        user=user,
        password=password,
        protocol=protocol,
        no_cleanup=no_cleanup,
        extra_args=extra_args,
        quiet=True,
    )
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.exit_code
