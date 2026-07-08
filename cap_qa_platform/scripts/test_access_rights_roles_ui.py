#!/usr/bin/env python3
"""
Playwright UI smoke for access_rights_management roles.

Companion to access_rights_management/scripts/test_access_rights_roles_rpc.py.

Verdicts use live **ir.model.access** and **ir.rule** from the database for each
role's groups (same basis as the RPC script). UI is only compared against that —
loading an app menu without RPC read access is **not** flagged as VIOLATES.

Examples::

    cd cap_qa_platform

    python3 scripts/test_access_rights_roles_ui.py \\
        --url http://localhost:1919/ \\
        --db odoo19_captivea2 \\
        --user admin1 --password a

    python3 scripts/test_access_rights_roles_ui.py \\
        --roles President "Team Manager" \\
        --report-file /tmp/access_ui_breaks.json

    python3 scripts/test_access_rights_roles_ui.py --roles-from db -v
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from cap_qa_platform.paths import ROLES_DATA_XML  # noqa: E402
from cap_qa_platform.rpc.client import OdooRPCClient  # noqa: E402
from cap_qa_platform.rpc.roles import parse_roles_from_xml  # noqa: E402
from cap_qa_platform.ui.access_rights.runner import (  # noqa: E402
    AccessRightsRoleUITest,
)
from cap_qa_platform.rpc.role_manager import TEST_USER_LOGIN, TEST_USER_PASSWORD  # noqa: E402

DEFAULT_URL = "http://localhost:8069"
DEFAULT_DB = "odoo"
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "admin"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Playwright UI access smoke for access_rights_management roles",
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--user", default=DEFAULT_USER, help="Admin username")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Admin password")
    parser.add_argument("--protocol", choices=["jsonrpc", "xmlrpc"], default="jsonrpc")
    parser.add_argument("--test-login", default=TEST_USER_LOGIN)
    parser.add_argument("--test-password", default=TEST_USER_PASSWORD)
    parser.add_argument("--roles-xml", default=str(ROLES_DATA_XML))
    parser.add_argument("--roles", nargs="+", metavar="NAME")
    parser.add_argument("--roles-from", choices=["xml", "db"], default="xml")
    parser.add_argument("--report-file", default="")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    role_defs = parse_roles_from_xml(Path(args.roles_xml))
    admin = OdooRPCClient(args.url, args.db, args.user, args.password, args.protocol)
    try:
        uid = admin.authenticate()
        print(f"Admin authenticated uid={uid}")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    runner = AccessRightsRoleUITest(
        admin=admin,
        url=args.url,
        db=args.db,
        role_defs=role_defs,
        roles_from=args.roles_from,
        role_filter=args.roles,
        test_login=args.test_login,
        test_password=args.test_password,
        report_file=args.report_file or None,
        verbose=args.verbose,
    )
    ok = runner.run()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
