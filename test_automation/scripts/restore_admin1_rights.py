#!/usr/bin/env python3
"""Restore admin1 to classic internal admin (Settings) without business role lines."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from test_automation.rpc.client import OdooRPCClient  # noqa: E402

DEFAULT_URL = os.environ.get("ODOO_URL", "http://localhost:8069")
DEFAULT_DB = os.environ.get("ODOO_DB", "odoo")
DEFAULT_USER = os.environ.get("ODOO_USER", "admin1")
DEFAULT_PASSWORD = os.environ.get("ODOO_PASSWORD", "admin")

CORE_GROUPS = (
    ("base", "group_user"),
    ("base", "group_system"),
)


def _xmlid_group_id(admin: OdooRPCClient, module: str, name: str) -> int:
    rows = admin.search(
        "ir.model.data",
        [("module", "=", module), ("name", "=", name)],
        limit=1,
    )
    if not rows:
        raise RuntimeError(f"Missing xmlid {module}.{name}")
    return admin.read("ir.model.data", rows, ["res_id"])[0]["res_id"]


def restore_admin(admin: OdooRPCClient, login: str, *, backup_file: Path | None) -> dict:
    user_ids = admin.search("res.users", [("login", "=", login)], limit=1)
    if not user_ids:
        raise RuntimeError(f"User {login!r} not found")
    user_id = user_ids[0]

    line_ids = admin.search("res.users.role.line", [("user_id", "=", user_id)])
    backup = {
        "login": login,
        "user_id": user_id,
        "role_lines": [],
        "group_ids": [],
    }
    if line_ids:
        backup["role_lines"] = admin.read(
            "res.users.role.line",
            line_ids,
            ["role_id", "date_from", "date_to"],
        )
    backup["group_ids"] = admin.read("res.users", [user_id], ["group_ids"])[0]["group_ids"]

    if backup_file:
        backup_file.write_text(json.dumps(backup, indent=2, default=str), encoding="utf-8")

    if line_ids:
        admin.unlink("res.users.role.line", line_ids)
    admin.execute_kw("res.users", "set_groups_from_roles", [[user_id]], {})

    core_ids = [_xmlid_group_id(admin, m, n) for m, n in CORE_GROUPS]
    admin.write(
        "res.users",
        [user_id],
        {
            "share": False,
            "group_ids": [(4, gid) for gid in core_ids],
        },
    )

    user = admin.read(
        "res.users",
        [user_id],
        ["login", "share", "group_ids", "role_line_ids"],
    )[0]
    has_system = _xmlid_group_id(admin, "base", "group_system") in user["group_ids"]
    return {
        "user_id": user_id,
        "login": user["login"],
        "share": user["share"],
        "group_count": len(user["group_ids"]),
        "role_line_count": len(user.get("role_line_ids") or []),
        "has_group_system": has_system,
        "backup_file": str(backup_file) if backup_file else None,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Restore admin user to classic Settings rights")
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--user", default=DEFAULT_USER, help="Admin login to restore (default: admin1)")
    p.add_argument("--password", default=DEFAULT_PASSWORD)
    p.add_argument("--login", default="admin1", help="Target user login to fix")
    p.add_argument(
        "--backup-file",
        default="/tmp/admin1_rights_backup.json",
        help="Save previous roles/groups before restore",
    )
    args = p.parse_args()

    admin = OdooRPCClient(args.url, args.db, args.user, args.password)
    admin.authenticate()
    result = restore_admin(admin, args.login, backup_file=Path(args.backup_file))
    print(json.dumps(result, indent=2))
    if not result["has_group_system"] or result["share"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
