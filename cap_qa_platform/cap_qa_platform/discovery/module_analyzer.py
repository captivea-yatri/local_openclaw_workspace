"""Analyze an Odoo module folder for test scaffolding."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from cap_qa_platform.discovery.module_scanner import _module_has_rpc_test, _parse_manifest, _scenario_covers_module
from cap_qa_platform.paths import ADDONS_ROOT


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _extract_llm_models(llm_providers_text: str) -> list[str]:
    idx = llm_providers_text.find("CUSTOM_PROVIDER")
    if idx < 0:
        return []
    segment = llm_providers_text[idx : idx + 2500]
    models = re.findall(
        r'^\s*\(\s*"([^"]+)"\s*,\s*"[^"]*"\s*\)\s*,?\s*$',
        segment,
        re.MULTILINE,
    )
    return models


def _extract_default_llm(llm_providers_text: str) -> str | None:
    match = re.search(r'^DEFAULT_LLM\s*=\s*"([^"]+)"', llm_providers_text, re.MULTILINE)
    if match:
        return match.group(1)
    match = re.search(r'^DEFAULT_FREE_LLM\s*=\s*"([^"]+)"', llm_providers_text, re.MULTILINE)
    return match.group(1) if match else None


def _extract_param_api_key(llm_providers_text: str, settings_text: str, technical_name: str) -> str | None:
    match = re.search(r'PARAM_API_KEY\s*=\s*"([^"]+)"', llm_providers_text)
    if match:
        return match.group(1)
    match = re.search(r'PARAM_\w*KEY\s*=\s*"([^"]+)"', llm_providers_text)
    if match:
        return match.group(1)
    for _, param in _extract_config_fields(settings_text).items():
        if param and param.endswith(".api_key"):
            return param
    return f"{technical_name}.api_key"


def _extract_config_fields(settings_text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for match in re.finditer(
        r"(\w+)\s*=\s*fields\.\w+\([^)]*config_parameter\s*=\s*[\"']([^\"']+)[\"']",
        settings_text,
        re.MULTILINE,
    ):
        fields[match.group(1)] = match.group(2)
    for match in re.finditer(
        r"(\w+_key_enabled)\s*=\s*fields\.Boolean",
        settings_text,
    ):
        fields.setdefault(match.group(1), "")
    return fields


def _detect_module_type(module_dir: Path, manifest: dict, llm_text: str) -> str:
    depends = set(manifest.get("depends") or [])
    name = module_dir.name
    if (depends & {"ai", "ai_app"}) and (llm_text or name.startswith("connect_") or "ai" in name.lower()):
        return "ai_connector"
    if (module_dir / "scripts").is_dir():
        return "script_module"
    return "generic"


def analyze_module(technical_name: str) -> dict:
    module_dir = ADDONS_ROOT / technical_name
    if not module_dir.is_dir():
        raise FileNotFoundError(f"Module not found: {technical_name} ({module_dir})")

    manifest_path = module_dir / "__manifest__.py"
    manifest = _parse_manifest(manifest_path) or {}

    llm_path = module_dir / "utils" / "llm_providers.py"
    settings_path = module_dir / "models" / "res_config_settings.py"
    llm_text = _read_text(llm_path)
    settings_text = _read_text(settings_path)

    module_type = _detect_module_type(module_dir, manifest, llm_text)
    llm_models = _extract_llm_models(llm_text)
    param_api_key = _extract_param_api_key(llm_text, settings_text, technical_name) if llm_text or settings_text else None

    config_fields = _extract_config_fields(settings_text)

    models_dir = module_dir / "models"
    model_files = sorted(p.name for p in models_dir.glob("*.py") if p.name != "__init__.py") if models_dir.is_dir() else []

    return {
        "technical_name": technical_name,
        "name": manifest.get("name", technical_name),
        "module_type": module_type,
        "depends": list(manifest.get("depends") or []),
        "version": manifest.get("version", ""),
        "has_rpc_test": _module_has_rpc_test(module_dir, technical_name),
        "catalog_scenarios": _scenario_covers_module(technical_name),
        "paths": {
            "module_dir": str(module_dir),
            "manifest": str(manifest_path),
            "llm_providers": str(llm_path) if llm_path.is_file() else None,
            "settings": str(settings_path) if settings_path.is_file() else None,
        },
        "ai_connector": {
            "param_api_key": param_api_key,
            "default_llm": _extract_default_llm(llm_text),
            "llm_models": llm_models,
            "config_fields": config_fields,
        },
        "model_files": model_files,
        "scaffold_ready": module_type == "ai_connector" and bool(llm_models),
    }
