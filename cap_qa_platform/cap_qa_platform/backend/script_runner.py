"""Run bundled/module RPC scripts via subprocess."""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from cap_qa_platform.catalog import ScenarioEntry


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
        return text if len(text) <= max_chars else "..." + text[-max_chars:]


def run_script(
    entry: ScenarioEntry,
    *,
    url: str,
    db: str,
    user: str,
    password: str,
    protocol: str = "jsonrpc",
    extra_args: list[str] | None = None,
    timeout: int = 600,
) -> ScriptRunResult:
    script = entry.resolved_script()
    if script is None or not script.is_file():
        raise FileNotFoundError(f"Script not found for {entry.id}: {script}")

    cmd = [
        sys.executable,
        str(script),
        "--url",
        url,
        "--db",
        db,
        "--user",
        user,
        "--password",
        password,
        f"--{entry.protocol_flag}",
        protocol,
    ]
    cmd.extend(entry.extra_args)
    if extra_args:
        cmd.extend(extra_args)

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return ScriptRunResult(proc.returncode, proc.stdout, proc.stderr)
