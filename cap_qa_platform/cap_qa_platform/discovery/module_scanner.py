"""Scan custom_addons for Odoo modules and QA coverage gaps."""
from __future__ import annotations

import ast
from pathlib import Path

from cap_qa_platform.catalog import ALL_BY_ID, ALL_SCENARIO_IDS
from cap_qa_platform.paths import ADDONS_ROOT


def _parse_manifest(path: Path) -> dict | None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Dict):
            return ast.literal_eval(node.value)
    return None


def _module_has_rpc_test(module_dir: Path, technical_name: str) -> bool:
    patterns = (
        module_dir / "models" / f"test_{technical_name}_rpc.py",
        module_dir / f"models/test_{technical_name}_rpc.py",
    )
    if any(p.is_file() for p in patterns):
        return True
    scripts = list(module_dir.glob("scripts/test_*_rpc.py"))
    return bool(scripts)


def _scenario_covers_module(technical_name: str) -> list[str]:
    hits = []
    for sid in ALL_SCENARIO_IDS:
        entry = ALL_BY_ID[sid]
        if technical_name in entry.modules:
            hits.append(sid)
    return hits


def discover_modules(*, include_tested: bool = True) -> dict:
    """Return Odoo modules under custom_addons with QA coverage status."""
    skip_dirs = {
        "test_automation",
        "cap_qa_platform",
        "__pycache__",
        ".git",
    }

    all_modules: list[dict] = []
    for child in sorted(ADDONS_ROOT.iterdir()):
        if not child.is_dir() or child.name in skip_dirs or child.name.startswith("."):
            continue
        manifest_path = child / "__manifest__.py"
        if not manifest_path.is_file():
            continue

        manifest = _parse_manifest(manifest_path) or {}
        technical_name = child.name
        scenarios = _scenario_covers_module(technical_name)
        has_rpc = _module_has_rpc_test(child, technical_name)

        row = {
            "technical_name": technical_name,
            "name": manifest.get("name", technical_name),
            "depends": list(manifest.get("depends") or []),
            "version": manifest.get("version", ""),
            "has_rpc_test": has_rpc,
            "catalog_scenarios": scenarios,
            "qa_covered": bool(scenarios),
        }
        all_modules.append(row)

    tested = [m for m in all_modules if m["qa_covered"]]
    untested = [m for m in all_modules if not m["qa_covered"]]
    modules = all_modules if include_tested else untested

    return {
        "addons_root": str(ADDONS_ROOT),
        "total_modules": len(all_modules),
        "tested_count": len(tested),
        "untested_count": len(untested),
        "untested": [m["technical_name"] for m in untested],
        "modules": modules,
    }
