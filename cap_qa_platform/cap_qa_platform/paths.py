"""Filesystem paths for cap_qa_platform (standalone — no test_automation imports)."""
from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
ADDONS_ROOT = PROJECT_ROOT.parent
EXPECTATIONS_DIR = PACKAGE_ROOT / "expectations"
UI_DIR = PACKAGE_ROOT / "ui"
ROLES_DATA_XML = (
    ADDONS_ROOT / "access_rights_management" / "data" / "roles_data.xml"
)
# Read-only reference to existing bundled RPC scripts (we do not write there).
LEGACY_BUNDLED_SCRIPTS = ADDONS_ROOT / "test_automation" / "bundled_scripts"
