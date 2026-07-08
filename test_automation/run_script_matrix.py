#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Thin wrapper — delegates to run_matrix.py (script scenarios × roles)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DIR = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

MATRIX = _DIR / "run_matrix.py"


def main() -> int:
    forwarded: list[str] = []
    for arg in sys.argv[1:]:
        if arg == "--all-scenarios":
            forwarded.append("--all-scripts")
        else:
            forwarded.append(arg)
    if not any(a in ("--all-scripts", "--scenario") for a in forwarded):
        forwarded.insert(0, "--all-scripts")
    return subprocess.call([sys.executable, str(MATRIX), *forwarded])


if __name__ == "__main__":
    sys.exit(main())
