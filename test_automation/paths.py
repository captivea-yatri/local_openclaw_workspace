"""Path resolution for portable test_automation package."""
from __future__ import annotations

import os
from pathlib import Path

# Directory containing this package (test_automation/)
PACKAGE_ROOT = Path(__file__).resolve().parent

# Parent of test_automation — default: custom_addons repo root
ADDONS_ROOT = Path(os.environ.get("CUSTOM_ADDONS_ROOT", PACKAGE_ROOT.parent)).resolve()

BUNDLED_SCRIPTS = PACKAGE_ROOT / "bundled_scripts"
EXPECTATIONS = PACKAGE_ROOT / "expectations"
EXPECTATIONS_SCRIPTS = EXPECTATIONS / "scripts"
ROLES_DATA_XML = ADDONS_ROOT / "access_rights_management" / "data" / "roles_data.xml"
