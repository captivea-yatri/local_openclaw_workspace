"""Role discovery from access_rights_management/data/roles_data.xml or database."""
from __future__ import annotations

import re
from pathlib import Path

from .client import OdooRPCClient

from test_automation.paths import ROLES_DATA_XML as _DEFAULT_ROLES_XML

MODULE_NAME = "access_rights_management"
ROLES_DATA_XML = _DEFAULT_ROLES_XML


def parse_roles_from_xml(xml_path: Path | None = None) -> list[tuple[str, str]]:
    path = xml_path or ROLES_DATA_XML
    if not path.is_file():
        raise FileNotFoundError(f"roles_data.xml not found: {path}")
    content = path.read_text(encoding="utf-8")
    pattern = (
        r'<record id="([^"]+)" model="res\.users\.role">\s*'
        r'<field name="name">([^<]+)</field>'
    )
    return [(m.group(1), m.group(2).strip()) for m in re.finditer(pattern, content)]


def resolve_role_ids(
    admin: OdooRPCClient, role_defs: list[tuple[str, str]]
) -> list[dict]:
    roles = []
    missing = []
    for xml_id, name in role_defs:
        data_ids = admin.search(
            "ir.model.data",
            [
                ("module", "=", MODULE_NAME),
                ("name", "=", xml_id),
                ("model", "=", "res.users.role"),
            ],
            limit=1,
        )
        if data_ids:
            data = admin.read("ir.model.data", data_ids, ["res_id"])[0]
            roles.append({"xml_id": xml_id, "name": name, "id": data["res_id"]})
        else:
            role_ids = admin.search("res.users.role", [("name", "=", name)], limit=1)
            if role_ids:
                roles.append({"xml_id": xml_id, "name": name, "id": role_ids[0]})
            else:
                missing.append(name)
    if missing:
        print(f"[WARN] Roles not found in database ({len(missing)}): {', '.join(missing)}")
    return roles


def resolve_all_roles_from_db(admin: OdooRPCClient) -> list[dict]:
    role_ids = admin.search("res.users.role", [], order="name")
    if not role_ids:
        return []
    records = admin.read("res.users.role", role_ids, ["name"])
    return [{"xml_id": "", "name": rec["name"], "id": rec["id"]} for rec in records]


def resolve_roles(
    admin: OdooRPCClient,
    role_defs: list[tuple[str, str]],
    roles_from: str,
) -> list[dict]:
    if roles_from == "db":
        return resolve_all_roles_from_db(admin)
    return resolve_role_ids(admin, role_defs)
