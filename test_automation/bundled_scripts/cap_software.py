#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone RPC test for cap_software (Odoo 19).

No odoo-bin / shell required. Run with plain Python 3:

    python3 models/test_cap_software_rpc.py
    python3 models/test_cap_software_rpc.py --protocol xmlrpc
    python3 models/test_cap_software_rpc.py --url http://localhost:8069 --db odoo --user admin --password admin

Tests custom fields and workflows via public RPC APIs using exact model/field names from:
  - models/software.py
  - models/software_version.py
  - models/project.py
  - models/crm_lead.py
"""
from __future__ import annotations

import argparse
import json
import sys
import xmlrpc.client
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Configuration (override via CLI args)
# ---------------------------------------------------------------------------
DEFAULT_URL = "http://localhost:8069"
DEFAULT_DB = "odoo"
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "admin"
DEFAULT_PROTOCOL = "jsonrpc"  # jsonrpc | xmlrpc

MODULE_NAME = "cap_software"

# ---------------------------------------------------------------------------
# Technical names from models/software.py
# ---------------------------------------------------------------------------
MODEL_SOFTWARE = "software.software"
FIELD_SOFTWARE_NAME = "name"

# ---------------------------------------------------------------------------
# Technical names from models/software_version.py
# ---------------------------------------------------------------------------
MODEL_SOFTWARE_VERSION = "software.version"
FIELD_VERSION_SOFTWARE_ID = "software_id"
FIELD_VERSION_NUMBER = "version"
FIELD_VERSION_NAME = "name"

# ---------------------------------------------------------------------------
# Technical names from models/project.py
# ---------------------------------------------------------------------------
MODEL_PROJECT = "project.project"
FIELD_PROJECT_SOFTWARE_VERSION = "software_version_id"

# ---------------------------------------------------------------------------
# Technical names from models/crm_lead.py
# ---------------------------------------------------------------------------
MODEL_CRM_LEAD = "crm.lead"
FIELD_LEAD_SOFTWARE = "software_id"


class OdooRPCClient:
    """Thin Odoo 19 RPC client (JSON-RPC or XML-RPC)."""

    def __init__(self, url: str, db: str, username: str, password: str, protocol: str = "jsonrpc"):
        self.url = url.rstrip("/")
        self.db = db
        self.username = username
        self.password = password
        self.protocol = protocol.lower()
        self.uid: int | None = None
        self._json_id = 0
        self._xml_common = None
        self._xml_models = None

    def authenticate(self) -> int:
        if self.protocol == "xmlrpc":
            self._xml_common = xmlrpc.client.ServerProxy(
                f"{self.url}/xmlrpc/2/common", allow_none=True
            )
            self._xml_models = xmlrpc.client.ServerProxy(
                f"{self.url}/xmlrpc/2/object", allow_none=True
            )
            uid = self._xml_common.authenticate(self.db, self.username, self.password, {})
            if not uid:
                raise RuntimeError(
                    "Authentication failed. Check URL, database, username, and password."
                )
            self.uid = uid
            return uid

        uid = self._jsonrpc(
            "common", "authenticate", [self.db, self.username, self.password, {}]
        )
        if not uid:
            raise RuntimeError(
                "Authentication failed. Check URL, database, username, and password."
            )
        self.uid = uid
        return uid

    def _jsonrpc(self, service: str, method: str, args: list) -> Any:
        self._json_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"service": service, "method": method, "args": args},
            "id": self._json_id,
        }
        req = Request(
            f"{self.url}/jsonrpc",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"HTTP error {exc.code}: {exc.reason}") from exc
        except URLError as exc:
            raise RuntimeError(f"Cannot reach Odoo at {self.url}: {exc}") from exc

        if body.get("error"):
            err = body["error"]
            msg = err.get("data", {}).get("message") or err.get("message") or str(err)
            raise RuntimeError(f"Odoo RPC error: {msg}")
        return body.get("result")

    def execute_kw(
        self,
        model: str,
        method: str,
        args: list | None = None,
        kwargs: dict | None = None,
    ) -> Any:
        if self.uid is None:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        args = args or []
        kwargs = kwargs or {}
        if self.protocol == "xmlrpc":
            return self._xml_models.execute_kw(
                self.db, self.uid, self.password, model, method, args, kwargs
            )
        return self._jsonrpc(
            "object",
            "execute_kw",
            [self.db, self.uid, self.password, model, method, args, kwargs],
        )

    def search(
        self,
        model: str,
        domain: list,
        limit: int | None = None,
        order: str | None = None,
    ) -> list[int]:
        kwargs: dict[str, Any] = {}
        if limit is not None:
            kwargs["limit"] = limit
        if order:
            kwargs["order"] = order
        return self.execute_kw(model, "search", [domain], kwargs)

    def read(self, model: str, ids: list[int], fields: list[str]) -> list[dict]:
        return self.execute_kw(model, "read", [ids, fields])

    def create(self, model: str, vals: dict) -> int:
        return self.execute_kw(model, "create", [vals])

    def write(self, model: str, ids: list[int], vals: dict) -> bool:
        return self.execute_kw(model, "write", [ids, vals])

    def unlink(self, model: str, ids: list[int]) -> bool:
        return self.execute_kw(model, "unlink", [ids])

    def fields_get(self, model: str, fields: list[str] | None = None) -> dict:
        return self.execute_kw(model, "fields_get", [fields or []], {})


class CapSoftwareRPCTest:
    """End-to-end cap_software workflow test via RPC."""

    def __init__(self, client: OdooRPCClient):
        self.client = client
        self.passed = 0
        self.failed = 0
        self._cleanup_ids: dict[str, list[int]] = {
            MODEL_CRM_LEAD: [],
            MODEL_PROJECT: [],
            MODEL_SOFTWARE_VERSION: [],
            MODEL_SOFTWARE: [],
        }

    def _ok(self, label: str, condition: bool, detail: str = "") -> bool:
        status = "PASS" if condition else "FAIL"
        msg = f"[{status}] {label}"
        if detail:
            msg += f" -> {detail}"
        print(msg)
        if condition:
            self.passed += 1
        else:
            self.failed += 1
        return condition

    def _m2o_id(self, value: Any) -> int | None:
        if not value:
            return None
        return value[0] if isinstance(value, (list, tuple)) else value

    def _track(self, model: str, record_id: int) -> None:
        if model in self._cleanup_ids:
            self._cleanup_ids[model].append(record_id)

    def _module_installed(self) -> bool:
        module_ids = self.client.search(
            "ir.module.module",
            [("name", "=", MODULE_NAME), ("state", "=", "installed")],
        )
        return bool(module_ids)

    def _field_exists(self, model: str, field_name: str) -> bool:
        fields = self.client.fields_get(model, [field_name])
        return field_name in fields

    def _cleanup(self) -> None:
        order = [
            MODEL_CRM_LEAD,
            MODEL_PROJECT,
            MODEL_SOFTWARE_VERSION,
            MODEL_SOFTWARE,
        ]
        for model in order:
            ids = self._cleanup_ids.get(model, [])
            if ids:
                try:
                    self.client.unlink(model, ids)
                    print(f"  Cleaned up {len(ids)} {model} record(s)")
                except RuntimeError as exc:
                    print(f"  [WARN] cleanup {model} {ids}: {exc}")
            self._cleanup_ids[model] = []

    def run(self) -> bool:
        print("=" * 80)
        print("Cap Software — RPC Test (Odoo 19)")
        print(f"Module : {MODULE_NAME}")
        print(
            f"Protocol: {self.client.protocol.upper()} | DB: {self.client.db} | URL: {self.client.url}"
        )
        print("=" * 80)

        self._ok(f"Module {MODULE_NAME!r} installed", self._module_installed())

        # ------------------------------------------------------------------
        # software.software (models/software.py)
        # ------------------------------------------------------------------
        self._ok(
            f"{MODEL_SOFTWARE}.{FIELD_SOFTWARE_NAME} field exists",
            self._field_exists(MODEL_SOFTWARE, FIELD_SOFTWARE_NAME),
        )

        software_name = "RPC Test Software"
        software_id = self.client.create(MODEL_SOFTWARE, {FIELD_SOFTWARE_NAME: software_name})
        self._track(MODEL_SOFTWARE, software_id)
        software_data = self.client.read(
            MODEL_SOFTWARE, [software_id], [FIELD_SOFTWARE_NAME]
        )[0]
        self._ok(
            f"{MODEL_SOFTWARE} create/read",
            software_data[FIELD_SOFTWARE_NAME] == software_name,
            f"id={software_id}",
        )

        updated_name = "RPC Test Software Updated"
        self.client.write(MODEL_SOFTWARE, [software_id], {FIELD_SOFTWARE_NAME: updated_name})
        software_data = self.client.read(
            MODEL_SOFTWARE, [software_id], [FIELD_SOFTWARE_NAME]
        )[0]
        self._ok(
            f"{MODEL_SOFTWARE} write",
            software_data[FIELD_SOFTWARE_NAME] == updated_name,
        )

        # ------------------------------------------------------------------
        # software.version (models/software_version.py)
        # ------------------------------------------------------------------
        for field in (FIELD_VERSION_SOFTWARE_ID, FIELD_VERSION_NUMBER, FIELD_VERSION_NAME):
            self._ok(
                f"{MODEL_SOFTWARE_VERSION}.{field} field exists",
                self._field_exists(MODEL_SOFTWARE_VERSION, field),
            )

        version_number = 3
        version_id = self.client.create(
            MODEL_SOFTWARE_VERSION,
            {
                FIELD_VERSION_SOFTWARE_ID: software_id,
                FIELD_VERSION_NUMBER: version_number,
            },
        )
        self._track(MODEL_SOFTWARE_VERSION, version_id)
        version_data = self.client.read(
            MODEL_SOFTWARE_VERSION,
            [version_id],
            [FIELD_VERSION_NAME, FIELD_VERSION_SOFTWARE_ID, FIELD_VERSION_NUMBER],
        )[0]
        expected_name = f"{updated_name} V{version_number}"
        self._ok(
            f"{MODEL_SOFTWARE_VERSION}.{FIELD_VERSION_NAME} computed",
            version_data[FIELD_VERSION_NAME] == expected_name,
            f"got {version_data[FIELD_VERSION_NAME]!r}",
        )
        self._ok(
            f"{MODEL_SOFTWARE_VERSION}.{FIELD_VERSION_SOFTWARE_ID} link",
            self._m2o_id(version_data[FIELD_VERSION_SOFTWARE_ID]) == software_id,
        )
        self._ok(
            f"{MODEL_SOFTWARE_VERSION}.{FIELD_VERSION_NUMBER} stored",
            version_data[FIELD_VERSION_NUMBER] == version_number,
        )

        # Recompute name when software name changes (depends on software_id.name)
        self.client.write(MODEL_SOFTWARE, [software_id], {FIELD_SOFTWARE_NAME: "Renamed Software"})
        version_data = self.client.read(
            MODEL_SOFTWARE_VERSION, [version_id], [FIELD_VERSION_NAME]
        )[0]
        self._ok(
            f"{MODEL_SOFTWARE_VERSION}.{FIELD_VERSION_NAME} updates on software rename",
            version_data[FIELD_VERSION_NAME] == f"Renamed Software V{version_number}",
            f"got {version_data[FIELD_VERSION_NAME]!r}",
        )

        # ------------------------------------------------------------------
        # project.project (models/project.py)
        # ------------------------------------------------------------------
        self._ok(
            f"{MODEL_PROJECT}.{FIELD_PROJECT_SOFTWARE_VERSION} field exists",
            self._field_exists(MODEL_PROJECT, FIELD_PROJECT_SOFTWARE_VERSION),
        )

        project_id = self.client.create(
            MODEL_PROJECT,
            {
                "name": "RPC Cap Software Project",
                FIELD_PROJECT_SOFTWARE_VERSION: version_id,
            },
        )
        self._track(MODEL_PROJECT, project_id)
        project_data = self.client.read(
            MODEL_PROJECT, [project_id], [FIELD_PROJECT_SOFTWARE_VERSION, "name"]
        )[0]
        self._ok(
            f"{MODEL_PROJECT}.{FIELD_PROJECT_SOFTWARE_VERSION} assignable",
            self._m2o_id(project_data[FIELD_PROJECT_SOFTWARE_VERSION]) == version_id,
            f"project id={project_id}",
        )

        # ------------------------------------------------------------------
        # crm.lead (models/crm_lead.py)
        # ------------------------------------------------------------------
        self._ok(
            f"{MODEL_CRM_LEAD}.{FIELD_LEAD_SOFTWARE} field exists",
            self._field_exists(MODEL_CRM_LEAD, FIELD_LEAD_SOFTWARE),
        )

        lead_id = self.client.create(
            MODEL_CRM_LEAD,
            {
                "name": "RPC Cap Software Opportunity",
                "type": "opportunity",
                FIELD_LEAD_SOFTWARE: software_id,
            },
        )
        self._track(MODEL_CRM_LEAD, lead_id)
        lead_data = self.client.read(
            MODEL_CRM_LEAD, [lead_id], [FIELD_LEAD_SOFTWARE, "name", "type"]
        )[0]
        self._ok(
            f"{MODEL_CRM_LEAD}.{FIELD_LEAD_SOFTWARE} assignable",
            self._m2o_id(lead_data[FIELD_LEAD_SOFTWARE]) == software_id,
            f"lead id={lead_id}",
        )
        self._ok(
            f"{MODEL_CRM_LEAD} type is opportunity",
            lead_data.get("type") == "opportunity",
        )

        print("=" * 80)
        print(f"Result: {self.passed} passed, {self.failed} failed")
        print("=" * 80)

        self._cleanup()
        return self.failed == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RPC test for cap_software (Odoo 19)",
    )
    parser.add_argument("--url", default=DEFAULT_URL, help=f"Odoo URL (default: {DEFAULT_URL})")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"Database name (default: {DEFAULT_DB})")
    parser.add_argument("--user", default=DEFAULT_USER, help=f"Username (default: {DEFAULT_USER})")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Password")
    parser.add_argument(
        "--protocol",
        choices=["jsonrpc", "xmlrpc"],
        default=DEFAULT_PROTOCOL,
        help=f"RPC protocol (default: {DEFAULT_PROTOCOL})",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = OdooRPCClient(args.url, args.db, args.user, args.password, args.protocol)
    try:
        uid = client.authenticate()
        print(f"Authenticated uid={uid}")
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    success = CapSoftwareRPCTest(client).run()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
