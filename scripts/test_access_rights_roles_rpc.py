#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone RPC test for access_rights_management roles (Odoo 19).

Fully **dynamic**: models, groups, ``ir.model.access``, and ``ir.rule`` are loaded
live from the database. When a new model or access line is installed, the next run
picks it up automatically — no hardcoded model list required.

Uses ONE admin login + ONE test user. Each role is assigned individually and tested
for read / write / create / unlink (ACL + CRUD + record rules on existing data).

Outputs a **break report** showing exactly which role × model × operation fails,
plus an **OVERALL ACCESS VERDICT** per role:

- **CLEAN** — no security violations and no configuration gaps
- **GAPS** — ACL/config gaps (under-access) but no rule violations
- **VIOLATES** — over-access detected (user has permission ACL does not grant)

Run::

    # Test all 39 roles from data/roles_data.xml (default)
    python3 scripts/test_access_rights_roles_rpc.py \\
        --url http://localhost:8069 --db odoo --user admin --password admin

    # Remote / ngrok instance
    python3 scripts/test_access_rights_roles_rpc.py \\
        --url https://your-ngrok.ngrok-free.app \\
        --db odoo19_captivea2 --user admin1 --password a \\
        --report-file /tmp/access_breaks.json

    # All roles in database + JSON break report
    python3 scripts/test_access_rights_roles_rpc.py --roles-from db \\
        --report-file /tmp/access_breaks.json

    # Single role (faster)
    python3 scripts/test_access_rights_roles_rpc.py --roles President --skip-crud
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import xmlrpc.client
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_URL = "http://localhost:8069"
DEFAULT_DB = "odoo"
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "admin"
DEFAULT_PROTOCOL = "jsonrpc"
TEST_USER_LOGIN = "access_rights_role_tester"
TEST_USER_NAME = "Access Rights RPC Tester"
TEST_USER_PASSWORD = "access_rights_test"

MODULE_NAME = "access_rights_management"
ROLES_DATA_XML = Path(__file__).resolve().parent.parent / "data" / "roles_data.xml"

# Odoo x2many commands
CMD_CREATE = 0
CMD_LINK = 4
CMD_UNLINK = 3
CMD_CLEAR = 5
CMD_SET = 6

# Legacy static list (--smoke-mode fixed only).
SMOKE_MODELS_FIXED = [
    "crm.lead",
    "sale.order",
    "res.partner",
    "account.move",
    "project.project",
    "project.task",
    "helpdesk.ticket",
    "purchase.order",
    "hr.expense",
    "hr.applicant",
    "account.analytic.line",
    "gamification.goal",
    "survey.survey",
    "hr.employee",
    "approval.request",
]

PERM_FIELDS = ("perm_read", "perm_write", "perm_create", "perm_unlink")
PERM_TO_OP = {
    "perm_read": "read",
    "perm_write": "write",
    "perm_create": "create",
    "perm_unlink": "unlink",
}

# RPC errors that mean "model exists but user cannot read" vs "not searchable".
_ACCESS_DENIED_MARKERS = (
    "access error",
    "access denied",
    "access rights",
    "not allowed to access",
    "odoo.exceptions.accesserror",
)
_VALIDATION_MARKERS = (
    "validationerror",
    "usererror",
    "missingerror",
    "required",
    "mandatory field",
    "invalid field",
)

# Never create/unlink on these models during CRUD probes (production safety).
CRUD_MUTATION_BLOCKLIST = {
    "res.users",
    "res.groups",
    "res.company",
    "account.move",
    "account.payment",
    "sale.order",
    "purchase.order",
    "stock.picking",
    "hr.payslip",
    "mail.message",
    "mail.mail",
}

CRUD_MUTATION_PREFIX_BLOCKLIST = (
    "ir.",
    "base_import.",
    "web_editor.",
    "bus.",
)

# Break categories for overall verdict (lower = higher severity).
BREAK_CATEGORY_SECURITY = "security_violation"
BREAK_CATEGORY_CONFIG_GAP = "config_gap"
BREAK_CATEGORY_CRUD_DENIED = "crud_denied"
BREAK_CATEGORY_RECORD_SCOPE = "record_rule_scope"
BREAK_CATEGORY_RPC_BLOCKED = "rpc_blocked"
BREAK_CATEGORY_SMOKE = "smoke_limit"
BREAK_CATEGORY_OTHER = "other"

_CATEGORY_PRIORITY = {
    BREAK_CATEGORY_SECURITY: 0,
    BREAK_CATEGORY_CONFIG_GAP: 1,
    BREAK_CATEGORY_CRUD_DENIED: 2,
    BREAK_CATEGORY_RECORD_SCOPE: 3,
    BREAK_CATEGORY_RPC_BLOCKED: 4,
    BREAK_CATEGORY_SMOKE: 5,
    BREAK_CATEGORY_OTHER: 6,
}

_RPC_BLOCKED_MARKER = "rpc call on"
_RPC_BLOCKED_SUFFIX = "is not allowed"


# ---------------------------------------------------------------------------
# RPC client (JSON-RPC + XML-RPC, Odoo 19)
# ---------------------------------------------------------------------------
class OdooRPCClient:
    """Thin Odoo 19 RPC client supporting JSON-RPC and XML-RPC."""

    def __init__(
        self,
        url: str,
        db: str,
        username: str,
        password: str,
        protocol: str = "jsonrpc",
    ):
        self.url = url.rstrip("/")
        self.db = db
        self.username = username
        self.password = password
        self.protocol = protocol.lower()
        self.uid: int | None = None
        self._json_id = 0
        self._xml_common = None
        self._xml_models = None

    def authenticate(self, username: str | None = None, password: str | None = None) -> int:
        username = username or self.username
        password = password or self.password
        if self.protocol == "xmlrpc":
            self._xml_common = xmlrpc.client.ServerProxy(
                f"{self.url}/xmlrpc/2/common", allow_none=True
            )
            self._xml_models = xmlrpc.client.ServerProxy(
                f"{self.url}/xmlrpc/2/object", allow_none=True
            )
            uid = self._xml_common.authenticate(self.db, username, password, {})
        else:
            uid = self._jsonrpc(
                "common", "authenticate", [self.db, username, password, {}]
            )
        if not uid:
            raise RuntimeError(
                f"Authentication failed for {username!r}. "
                "Check URL, database, username, and password."
            )
        self.uid = uid
        self.username = username
        self.password = password
        return uid

    def _jsonrpc(self, service: str, method: str, args: list) -> Any:
        self._json_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"service": service, "method": method, "args": args},
            "id": self._json_id,
        }
        headers = {"Content-Type": "application/json"}
        if "ngrok" in self.url:
            headers["ngrok-skip-browser-warning"] = "true"
        req = Request(
            f"{self.url}/jsonrpc",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(req, timeout=180) as resp:
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

    def create(self, model: str, vals: dict, context: dict | None = None) -> int:
        kwargs = {"context": context} if context else {}
        return self.execute_kw(model, "create", [vals], kwargs)

    def write(
        self, model: str, ids: list[int], vals: dict, context: dict | None = None
    ) -> bool:
        kwargs = {"context": context} if context else {}
        return self.execute_kw(model, "write", [ids, vals], kwargs)

    def unlink(self, model: str, ids: list[int]) -> bool:
        return self.execute_kw(model, "unlink", [ids])


# ---------------------------------------------------------------------------
# Role definitions from data/roles_data.xml
# ---------------------------------------------------------------------------
def parse_roles_from_xml(xml_path: Path) -> list[tuple[str, str]]:
    """Return [(xml_id, role_name), ...] from roles_data.xml."""
    if not xml_path.is_file():
        raise FileNotFoundError(f"roles_data.xml not found: {xml_path}")
    content = xml_path.read_text(encoding="utf-8")
    pattern = (
        r'<record id="([^"]+)" model="res\.users\.role">\s*'
        r'<field name="name">([^<]+)</field>'
    )
    return [(m.group(1), m.group(2).strip()) for m in re.finditer(pattern, content)]


def resolve_all_roles_from_db(admin: OdooRPCClient) -> list[dict]:
    """Load every res.users.role from the database (fully dynamic)."""
    role_ids = admin.search("res.users.role", [], order="name")
    if not role_ids:
        return []
    records = admin.read("res.users.role", role_ids, ["name"])
    return [
        {"xml_id": "", "name": rec["name"], "id": rec["id"]}
        for rec in records
    ]


def resolve_role_ids(admin: OdooRPCClient, role_defs: list[tuple[str, str]]) -> list[dict]:
    """Map xml ids to res.users.role records in the database."""
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


def resolve_roles(
    admin: OdooRPCClient,
    role_defs: list[tuple[str, str]],
    roles_from: str,
) -> list[dict]:
    if roles_from == "db":
        return resolve_all_roles_from_db(admin)
    return resolve_role_ids(admin, role_defs)


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------
class AccessRightsRoleRPCTest:
    def __init__(
        self,
        admin: OdooRPCClient,
        test_login: str,
        test_password: str,
        role_defs: list[tuple[str, str]],
        roles_from: str = "xml",
        role_filter: list[str] | None = None,
        report_file: str | None = None,
        skip_smoke: bool = False,
        smoke_mode: str = "access",
        skip_crud: bool = False,
        skip_rules: bool = False,
        rule_sample_size: int = 5,
        allow_destructive: bool = False,
        verbose: bool = False,
    ):
        self.admin = admin
        self.test_login = test_login
        self.test_password = test_password
        self.role_defs = role_defs
        self.roles_from = roles_from
        self.role_filter = role_filter
        self.report_file = report_file
        self.skip_smoke = skip_smoke
        self.smoke_mode = smoke_mode
        self.skip_crud = skip_crud
        self.skip_rules = skip_rules
        self.rule_sample_size = rule_sample_size
        self.allow_destructive = allow_destructive
        self.verbose = verbose
        self.test_user_id: int | None = None
        self._original_role_lines: list[dict] = []
        self._ir_models_cache: list[dict] | None = None
        self._created_record_ids: dict[str, list[int]] = defaultdict(list)
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.role_results: dict[str, dict] = {}
        self.all_breaks: list[dict[str, Any]] = []
        self.breaks_by_role: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.breaks_by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._role_model_cache: dict[int, str] = {}
        self._rpc_disabled_models: set[str] = set()
        self._any_access_violation = False

    def _ok(self, label: str, condition: bool, detail: str = "") -> bool:
        status = "PASS" if condition else "FAIL"
        msg = f"  [{status}] {label}"
        if detail:
            msg += f" -> {detail}"
        if self.verbose or not condition:
            print(msg)
        if condition:
            self.passed += 1
        else:
            self.failed += 1
        return condition

    def _skip(self, label: str, detail: str = "") -> None:
        msg = f"  [SKIP] {label}"
        if detail:
            msg += f" -> {detail}"
        print(msg)
        self.skipped += 1

    def _record_break(
        self,
        role_name: str,
        role_id: int,
        model: str,
        operation: str,
        layer: str,
        message: str,
        rules: list[str] | None = None,
        category: str | None = None,
    ) -> None:
        entry = {
            "role": role_name,
            "role_id": role_id,
            "model": model,
            "operation": operation,
            "layer": layer,
            "message": message,
            "rules": rules or [],
            "category": category
            or self._categorize_break(layer, message, model),
        }
        self.all_breaks.append(entry)
        self.breaks_by_role[role_name].append(entry)
        self.breaks_by_model[model].append(entry)
        print(
            f"    [BREAK] {role_name} | {model}.{operation} | {entry['category']} | {message}"
        )
        if rules and self.verbose:
            print(f"            rules: {', '.join(rules[:5])}")
        self.failed += 1

    @staticmethod
    def _is_rpc_blocked_message(message: str) -> bool:
        msg = message.lower()
        return _RPC_BLOCKED_MARKER in msg and _RPC_BLOCKED_SUFFIX in msg

    def _categorize_break(self, layer: str, message: str, model: str) -> str:
        if layer == "security":
            return BREAK_CATEGORY_SECURITY
        if self._is_rpc_blocked_message(message) or model in self._rpc_disabled_models:
            if layer == "acl" or "check_access_rights denied" in message.lower():
                return BREAK_CATEGORY_RPC_BLOCKED
        if layer == "record_rule" or "write denied on visible record" in message:
            return BREAK_CATEGORY_RECORD_SCOPE
        if layer == "smoke":
            return BREAK_CATEGORY_SMOKE
        if layer == "crud":
            return BREAK_CATEGORY_CRUD_DENIED
        if layer == "acl":
            return BREAK_CATEGORY_CONFIG_GAP
        return BREAK_CATEGORY_OTHER

    def _load_rpc_disabled_models(self) -> set[str]:
        """Models where rpc_helper blocks all RPC (false positives for ACL checks)."""
        disabled: set[str] = set()
        try:
            rows = self.admin.execute_kw(
                "ir.model",
                "search_read",
                [[]],
                {"fields": ["model", "rpc_config"]},
            )
        except RuntimeError:
            return disabled
        for row in rows:
            config = row.get("rpc_config") or {}
            if isinstance(config, dict) and "all" in (config.get("disable") or []):
                disabled.add(row["model"])
        return disabled

    @staticmethod
    def _dedupe_breaks(breaks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep the highest-severity break per model × operation."""
        best: dict[tuple[str, str], dict[str, Any]] = {}
        for entry in breaks:
            key = (entry["model"], entry["operation"])
            cat = entry.get("category", BREAK_CATEGORY_OTHER)
            pri = _CATEGORY_PRIORITY.get(cat, 99)
            if key not in best or pri < _CATEGORY_PRIORITY.get(
                best[key].get("category", BREAK_CATEGORY_OTHER), 99
            ):
                best[key] = entry
        return list(best.values())

    def _compute_role_verdict(self, role_name: str) -> dict[str, Any]:
        breaks = self._dedupe_breaks(self.breaks_by_role.get(role_name, []))
        counts: dict[str, int] = defaultdict(int)
        for entry in breaks:
            counts[entry.get("category", BREAK_CATEGORY_OTHER)] += 1

        security = counts[BREAK_CATEGORY_SECURITY]
        config_gap = counts[BREAK_CATEGORY_CONFIG_GAP]
        crud_denied = counts[BREAK_CATEGORY_CRUD_DENIED]
        record_scope = counts[BREAK_CATEGORY_RECORD_SCOPE]
        rpc_blocked = counts[BREAK_CATEGORY_RPC_BLOCKED]
        smoke = counts[BREAK_CATEGORY_SMOKE]
        other = counts[BREAK_CATEGORY_OTHER]

        violates = security > 0
        actionable_gaps = config_gap + crud_denied

        if violates:
            verdict = "VIOLATES"
            summary = (
                f"VIOLATES access rules — {security} over-access issue(s) "
                f"(user has permission ACL does not grant)"
            )
        elif actionable_gaps:
            verdict = "GAPS"
            summary = (
                f"Does NOT violate rules, but {actionable_gaps} configuration gap(s) "
                f"(ACL grants access that checks deny)"
            )
        elif breaks:
            verdict = "CLEAN"
            summary = (
                f"Does NOT violate access rules — {len(breaks)} finding(s) are "
                f"expected scoping ({record_scope}), RPC limits ({rpc_blocked}), "
                f"or smoke noise ({smoke})"
            )
        else:
            verdict = "CLEAN"
            summary = "Does NOT violate access rules — no issues detected"

        return {
            "verdict": verdict,
            "violates_access_rules": violates,
            "summary": summary,
            "break_counts": dict(counts),
            "security_violations": security,
            "config_gaps": config_gap,
            "crud_denied": crud_denied,
            "record_rule_scope": record_scope,
            "rpc_blocked": rpc_blocked,
            "smoke_limit": smoke,
            "other": other,
            "unique_breaks": len(breaks),
        }

    def _print_overall_verdict(self) -> None:
        print("\n" + "=" * 80)
        print("OVERALL ACCESS VERDICT")
        print("=" * 80)
        any_violation = False
        for role_name, res in self.role_results.items():
            verdict = res.get("access_verdict", {})
            if not verdict:
                continue
            v = verdict["verdict"]
            if verdict["violates_access_rules"]:
                any_violation = True
            print(f"\n  {role_name}: {v}")
            print(f"    {verdict['summary']}")
            bc = verdict["break_counts"]
            if bc:
                parts = [f"{k}={v}" for k, v in sorted(bc.items()) if v]
                print(f"    Breakdown (deduped): {', '.join(parts)}")

        print("\n" + "-" * 80)
        if len(self.role_results) == 1:
            only = next(iter(self.role_results.values()))
            v = only.get("access_verdict", {})
            if v.get("violates_access_rules"):
                print("  RESULT: Role VIOLATES access rules (over-access detected).")
            elif v.get("verdict") == "GAPS":
                print("  RESULT: Role does NOT violate rules; configuration gaps found.")
            else:
                print("  RESULT: Role does NOT violate access rules.")
        else:
            violating = [
                n
                for n, r in self.role_results.items()
                if r.get("access_verdict", {}).get("violates_access_rules")
            ]
            if violating:
                print(
                    f"  RESULT: {len(violating)} role(s) VIOLATE access rules: "
                    f"{', '.join(violating)}"
                )
                any_violation = True
            else:
                print("  RESULT: No role violates access rules (no over-access detected).")
        print("=" * 80)
        self._any_access_violation = any_violation

    def _classify_rpc_error(self, exc: RuntimeError) -> str:
        msg = str(exc).lower()
        if self._is_rpc_blocked_message(msg):
            return "rpc_blocked"
        if any(marker in msg for marker in _ACCESS_DENIED_MARKERS):
            return "denied"
        if any(marker in msg for marker in _VALIDATION_MARKERS):
            return "validation"
        return "skip"

    def _check_access_outcome(
        self, client: OdooRPCClient, model: str, operation: str
    ) -> str:
        """Return allowed | denied | rpc_blocked | skip."""
        try:
            client.execute_kw(
                model,
                "check_access_rights",
                [operation],
                {"raise_exception": True},
            )
            return "allowed"
        except RuntimeError as exc:
            outcome = self._classify_rpc_error(exc)
            if outcome == "rpc_blocked":
                return "rpc_blocked"
            if outcome == "denied":
                return "denied"
            return "skip"

    def _expect_access_ok(self, client: OdooRPCClient, model: str, operation: str) -> bool:
        return self._check_access_outcome(client, model, operation) == "allowed"

    def _test_unexpected_access(
        self,
        tester: OdooRPCClient,
        model_perms: dict[str, dict[str, bool]],
        role_name: str,
        role_id: int,
        rules_by_model: dict[str, list[str]],
    ) -> int:
        """Detect over-access: ACL denies but check_access_rights allows."""
        violations = 0
        for model_name in sorted(model_perms):
            perms = model_perms[model_name]
            for op in ("read", "write", "create", "unlink"):
                if perms.get(op):
                    continue
                outcome = self._check_access_outcome(tester, model_name, op)
                if outcome != "allowed":
                    continue
                violations += 1
                self._record_break(
                    role_name,
                    role_id,
                    model_name,
                    op,
                    "security",
                    "ACL does not grant permission but check_access_rights allowed",
                    rules_by_model.get(model_name),
                    category=BREAK_CATEGORY_SECURITY,
                )
        if violations:
            print(f"  Over-access (security): {violations} violation(s)")
        else:
            print("  Over-access (security): 0 violations")
        return violations

    def _rpc_safe(
        self,
        client: OdooRPCClient,
        model: str,
        method: str,
        args: list | None = None,
        kwargs: dict | None = None,
    ) -> tuple[str, Any]:
        """Run RPC call; return (outcome, result). outcome: ok|denied|validation|skip."""
        try:
            result = client.execute_kw(model, method, args or [], kwargs or {})
            return "ok", result
        except RuntimeError as exc:
            return self._classify_rpc_error(exc), None

    def _search_result(self, client: OdooRPCClient, model: str) -> str:
        outcome, _ = self._rpc_safe(client, model, "search", [[]], {"limit": 1})
        return outcome if outcome in ("ok", "denied") else "skip"

    def _model_technical_name_cache(self, *rule_lists: list[dict]) -> dict[int, str]:
        """Map ir.model database id -> technical name (e.g. sale.order).

        ir.model.access / ir.rule ``model_id`` m2o reads as [id, display_name];
        RPC must use the technical ``model`` field, not the display name.
        """
        ir_model_ids: set[int] = set()
        for rules in rule_lists:
            for rule in rules:
                mid = rule.get("model_id")
                if mid:
                    ir_model_ids.add(mid[0] if isinstance(mid, (list, tuple)) else mid)
        if not ir_model_ids:
            return {}
        rows = self.admin.read("ir.model", list(ir_model_ids), ["model", "transient"])
        return {r["id"]: r["model"] for r in rows if not r.get("transient")}

    def _rule_model_technical(self, rule: dict) -> str | None:
        mid = rule.get("model_id")
        if not mid:
            return None
        ir_id = mid[0] if isinstance(mid, (list, tuple)) else mid
        return self._role_model_cache.get(ir_id)

    def _build_model_permissions(
        self, access_rules: list[dict]
    ) -> dict[str, dict[str, bool]]:
        """Merge ir.model.access rows into per-model CRUD flags."""
        perms: dict[str, dict[str, bool]] = defaultdict(
            lambda: {"read": False, "write": False, "create": False, "unlink": False}
        )
        for rule in access_rules:
            model_name = self._rule_model_technical(rule)
            if not model_name:
                continue
            for perm_field, op in PERM_TO_OP.items():
                if rule.get(perm_field):
                    perms[model_name][op] = True
        return dict(perms)

    def _mutation_allowed(self, model_name: str) -> bool:
        if model_name in CRUD_MUTATION_BLOCKLIST:
            return False
        return not any(model_name.startswith(p) for p in CRUD_MUTATION_PREFIX_BLOCKLIST)

    def _load_ir_models(self) -> list[dict]:
        """Admin: load non-transient models from ir.model (dynamic registry)."""
        if self._ir_models_cache is not None:
            return self._ir_models_cache
        model_ids = self.admin.search("ir.model", [], order="model")
        records = self.admin.read("ir.model", model_ids, ["model", "name", "transient"])
        self._ir_models_cache = [r for r in records if not r.get("transient")]
        return self._ir_models_cache

    def _ensure_test_user(self) -> int:
        existing = self.admin.search(
            "res.users", [("login", "=", self.test_login)], limit=1
        )
        if existing:
            user_id = existing[0]
            self.admin.write(
                "res.users",
                [user_id],
                {"password": self.test_password, "active": True},
            )
        else:
            user_id = self.admin.create(
                "res.users",
                {
                    "name": TEST_USER_NAME,
                    "login": self.test_login,
                    "password": self.test_password,
                    "group_ids": [(CMD_CLEAR, 0, 0)],
                },
            )
        self.test_user_id = user_id
        return user_id

    def _backup_role_lines(self) -> None:
        assert self.test_user_id is not None
        line_ids = self.admin.search(
            "res.users.role.line", [("user_id", "=", self.test_user_id)]
        )
        if line_ids:
            self._original_role_lines = self.admin.read(
                "res.users.role.line",
                line_ids,
                ["role_id", "date_from", "date_to"],
            )

    def _restore_role_lines(self) -> None:
        assert self.test_user_id is not None
        line_ids = self.admin.search(
            "res.users.role.line", [("user_id", "=", self.test_user_id)]
        )
        if line_ids:
            self.admin.unlink("res.users.role.line", line_ids)
        for line in self._original_role_lines:
            vals = {
                "user_id": self.test_user_id,
                "role_id": line["role_id"][0],
            }
            if line.get("date_from"):
                vals["date_from"] = line["date_from"]
            if line.get("date_to"):
                vals["date_to"] = line["date_to"]
            self.admin.create("res.users.role.line", vals)

    def _assign_single_role(self, role_id: int) -> None:
        assert self.test_user_id is not None
        line_ids = self.admin.search(
            "res.users.role.line", [("user_id", "=", self.test_user_id)]
        )
        if line_ids:
            self.admin.unlink("res.users.role.line", line_ids)
        self.admin.create(
            "res.users.role.line",
            {"user_id": self.test_user_id, "role_id": role_id},
        )
        # Force group sync (normally triggered by write hook on res.users).
        self.admin.execute_kw(
            "res.users",
            "set_groups_from_roles",
            [[self.test_user_id]],
            {},
        )

    def _verify_groups_synced(self, role_id: int) -> bool:
        assert self.test_user_id is not None
        user_groups = set(
            self.admin.read("res.users", [self.test_user_id], ["group_ids"])[0]["group_ids"]
        )
        role_data = self.admin.read(
            "res.users.role",
            [role_id],
            ["all_implied_ids", "implied_ids", "name"],
        )[0]
        expected = set(role_data.get("all_implied_ids") or role_data.get("implied_ids") or [])
        missing = expected - user_groups
        extra_note = ""
        if missing:
            extra_note = f"missing {len(missing)} group(s)"
        return self._ok(
            f"Groups synced for role {role_data['name']!r}",
            not missing,
            extra_note or f"{len(user_groups)} groups on user",
        )

    def _get_group_ids_for_role(self, role_id: int) -> tuple[set[int], str]:
        role_data = self.admin.read(
            "res.users.role",
            [role_id],
            ["all_implied_ids", "implied_ids", "name"],
        )[0]
        group_ids = set(
            role_data.get("all_implied_ids") or role_data.get("implied_ids") or []
        )
        return group_ids, role_data["name"]

    def _get_role_access_rules(self, role_id: int) -> list[dict]:
        """Dynamic: all ir.model.access rows for groups implied by the role."""
        group_ids, _ = self._get_group_ids_for_role(role_id)
        if not group_ids:
            return []
        access_ids = self.admin.search(
            "ir.model.access", [("group_id", "in", list(group_ids))]
        )
        if not access_ids:
            return []
        return self.admin.read(
            "ir.model.access",
            access_ids,
            ["name", "model_id", "group_id", *PERM_FIELDS],
        )

    def _get_role_record_rules(self, role_id: int) -> list[dict]:
        """Dynamic: all ir.rule rows linked to role groups."""
        group_ids, _ = self._get_group_ids_for_role(role_id)
        if not group_ids:
            return []
        rule_ids = self.admin.search(
            "ir.rule",
            [("groups", "in", list(group_ids)), ("active", "=", True)],
        )
        if not rule_ids:
            return []
        return self.admin.read(
            "ir.rule",
            rule_ids,
            [
                "name",
                "model_id",
                "domain_force",
                "groups",
                "perm_read",
                "perm_write",
                "perm_create",
                "perm_unlink",
            ],
        )

    @staticmethod
    def _rules_by_model(record_rules: list[dict], model_cache: dict[int, str]) -> dict[str, list[str]]:
        by_model: dict[str, list[str]] = defaultdict(list)
        for rule in record_rules:
            mid = rule.get("model_id")
            if not mid:
                continue
            ir_id = mid[0] if isinstance(mid, (list, tuple)) else mid
            technical = model_cache.get(ir_id)
            if technical:
                by_model[technical].append(rule.get("name") or "?")
        return dict(by_model)

    def _resolve_test_models(
        self,
        access_rules: list[dict],
        record_rules: list[dict],
    ) -> tuple[list[str], str]:
        """Models to test — always derived from live ACL + rules (+ optional ir.model)."""
        if self.smoke_mode == "fixed":
            return SMOKE_MODELS_FIXED, "static legacy list"
        if self.smoke_mode == "all":
            models = {r["model"] for r in self._load_ir_models()}
            source = f"ir.model ({len(models)} non-transient)"
        else:
            models = set()
            source = "groups → ir.model.access + ir.rule"
        for rule in access_rules:
            name = self._rule_model_technical(rule)
            if name:
                models.add(name)
        for rule in record_rules:
            mid = rule.get("model_id")
            if mid:
                ir_id = mid[0] if isinstance(mid, (list, tuple)) else mid
                name = self._role_model_cache.get(ir_id)
                if name:
                    models.add(name)
        return sorted(models), source

    def _build_model_permissions_from_access_and_rules(
        self,
        access_rules: list[dict],
        record_rules: list[dict],
    ) -> dict[str, dict[str, bool]]:
        perms = self._build_model_permissions(access_rules)
        for rule in record_rules:
            model_name = self._rule_model_technical(rule)
            if not model_name:
                continue
            if model_name not in perms:
                perms[model_name] = {
                    "read": False,
                    "write": False,
                    "create": False,
                    "unlink": False,
                }
            if rule.get("perm_read"):
                perms[model_name]["read"] = True
            if rule.get("perm_write"):
                perms[model_name]["write"] = True
            if rule.get("perm_create"):
                perms[model_name]["create"] = True
            if rule.get("perm_unlink"):
                perms[model_name]["unlink"] = True
        return perms

    def _test_access_rules_as_user(
        self,
        tester: OdooRPCClient,
        access_rules: list[dict],
        role_name: str,
        role_id: int,
        rules_by_model: dict[str, list[str]],
    ) -> tuple[int, int]:
        passed = failed = 0
        expected: dict[tuple[str, str], bool] = {}
        for rule in access_rules:
            model_name = self._rule_model_technical(rule)
            if not model_name:
                continue
            for perm_field, operation in PERM_TO_OP.items():
                if rule.get(perm_field):
                    expected[(model_name, operation)] = True

        for (model_name, operation), should_allow in sorted(expected.items()):
            allowed = self._expect_access_ok(tester, model_name, operation)
            if should_allow and allowed:
                passed += 1
                if self.verbose:
                    print(f"    [PASS ACL] {model_name}.{operation}")
            elif should_allow and not allowed:
                failed += 1
                self._record_break(
                    role_name,
                    role_id,
                    model_name,
                    operation,
                    "acl",
                    "ir.model.access grants permission but check_access_rights denied",
                    rules_by_model.get(model_name),
                )

        self.passed += passed
        return passed, failed

    def _admin_sample_record_ids(self, model_name: str) -> list[int]:
        outcome, ids = self._rpc_safe(
            self.admin, model_name, "search", [[]], {"limit": self.rule_sample_size, "order": "id desc"}
        )
        if outcome != "ok" or not ids:
            return []
        return ids

    def _test_crud_operations(
        self,
        tester: OdooRPCClient,
        model_perms: dict[str, dict[str, bool]],
        role_name: str,
        role_id: int,
        rules_by_model: dict[str, list[str]],
    ) -> dict[str, int]:
        """Operational CRUD tests aligned with dynamic ir.model.access for the role."""
        stats: dict[str, int] = defaultdict(int)

        for model_name in sorted(model_perms):
            perms = model_perms[model_name]
            if not any(perms.values()):
                continue
            model_rules = rules_by_model.get(model_name)

            if perms["read"]:
                if self._expect_access_ok(tester, model_name, "read"):
                    outcome, ids = self._rpc_safe(
                        tester, model_name, "search", [[]], {"limit": 1}
                    )
                    if outcome == "ok":
                        stats["read_pass"] += 1
                        if ids:
                            ro, _ = self._rpc_safe(
                                tester, model_name, "read", [ids, ["id"]]
                            )
                            if ro == "denied":
                                stats["read_fail"] += 1
                                self._record_break(
                                    role_name,
                                    role_id,
                                    model_name,
                                    "read",
                                    "crud",
                                    "search OK but read(ids) denied",
                                    model_rules,
                                )
                            elif ro == "skip":
                                stats["read_skip"] += 1
                    elif outcome == "denied":
                        stats["read_fail"] += 1
                        self._record_break(
                            role_name,
                            role_id,
                            model_name,
                            "read",
                            "crud",
                            "ACL read granted but search denied",
                            model_rules,
                        )
                    else:
                        stats["read_skip"] += 1
                else:
                    stats["read_fail"] += 1
                    self._record_break(
                        role_name,
                        role_id,
                        model_name,
                        "read",
                        "acl",
                        "perm_read in ACL but check_access_rights denied",
                        model_rules,
                    )

            if perms["write"]:
                if not self._expect_access_ok(tester, model_name, "write"):
                    stats["write_fail"] += 1
                    self._record_break(
                        role_name,
                        role_id,
                        model_name,
                        "write",
                        "acl",
                        "perm_write in ACL but check_access_rights denied",
                        model_rules,
                    )
                else:
                    _, user_ids = self._rpc_safe(
                        tester, model_name, "search", [[]], {"limit": 1}
                    )
                    if user_ids:
                        wo, _ = self._rpc_safe(
                            tester, model_name, "write", [[user_ids[0]], {}]
                        )
                        if wo == "ok":
                            stats["write_pass"] += 1
                        elif wo == "denied":
                            stats["write_fail"] += 1
                            self._record_break(
                                role_name,
                                role_id,
                                model_name,
                                "write",
                                "crud",
                                f"write denied on visible record {user_ids[0]}",
                                model_rules,
                            )
                        else:
                            stats["write_skip"] += 1
                    else:
                        stats["write_skip"] += 1

            if perms["create"]:
                if not self._expect_access_ok(tester, model_name, "create"):
                    stats["create_fail"] += 1
                    self._record_break(
                        role_name,
                        role_id,
                        model_name,
                        "create",
                        "acl",
                        "perm_create in ACL but check_access_rights denied",
                        model_rules,
                    )
                elif not self._mutation_allowed(model_name):
                    stats["create_skip"] += 1
                else:
                    co, new_id = self._rpc_safe(tester, model_name, "create", [{}])
                    if co == "ok" and new_id:
                        stats["create_pass"] += 1
                        self._created_record_ids[model_name].append(new_id)
                    elif co == "validation":
                        stats["create_pass"] += 1
                    elif co == "denied":
                        stats["create_fail"] += 1
                        self._record_break(
                            role_name,
                            role_id,
                            model_name,
                            "create",
                            "crud",
                            "create denied",
                            model_rules,
                        )
                    else:
                        stats["create_skip"] += 1

            if perms["unlink"]:
                if not self._expect_access_ok(tester, model_name, "unlink"):
                    stats["unlink_fail"] += 1
                    self._record_break(
                        role_name,
                        role_id,
                        model_name,
                        "unlink",
                        "acl",
                        "perm_unlink in ACL but check_access_rights denied",
                        model_rules,
                    )
                elif not self._mutation_allowed(model_name):
                    stats["unlink_skip"] += 1
                elif self._created_record_ids.get(model_name):
                    rid = self._created_record_ids[model_name][-1]
                    uo, _ = self._rpc_safe(tester, model_name, "unlink", [[rid]])
                    if uo == "ok":
                        stats["unlink_pass"] += 1
                        self._created_record_ids[model_name].pop()
                    elif uo == "denied":
                        stats["unlink_fail"] += 1
                        self._record_break(
                            role_name,
                            role_id,
                            model_name,
                            "unlink",
                            "crud",
                            "unlink denied on test-created record",
                            model_rules,
                        )
                    else:
                        stats["unlink_skip"] += 1
                elif self.allow_destructive:
                    _, user_ids = self._rpc_safe(
                        tester, model_name, "search", [[]], {"limit": 1}
                    )
                    if user_ids:
                        uo, _ = self._rpc_safe(
                            tester, model_name, "unlink", [[user_ids[0]]]
                        )
                        if uo == "ok":
                            stats["unlink_pass"] += 1
                        elif uo == "denied":
                            stats["unlink_fail"] += 1
                            self._record_break(
                                role_name,
                                role_id,
                                model_name,
                                "unlink",
                                "crud",
                                "unlink denied (destructive probe)",
                                model_rules,
                            )
                        else:
                            stats["unlink_skip"] += 1
                    else:
                        stats["unlink_skip"] += 1
                else:
                    stats["unlink_skip"] += 1

        for key, val in stats.items():
            if key.endswith("_pass"):
                self.passed += val
        return dict(stats)

    def _test_record_rules(
        self,
        tester: OdooRPCClient,
        model_perms: dict[str, dict[str, bool]],
        role_name: str,
        role_id: int,
        rules_by_model: dict[str, list[str]],
    ) -> dict[str, int]:
        """Probe record rules on existing data; record breaks when ACL/RPC disagree."""
        stats: dict[str, int] = defaultdict(int)

        for model_name in sorted(model_perms):
            perms = model_perms[model_name]
            if not perms.get("read"):
                continue

            admin_ids = self._admin_sample_record_ids(model_name)
            if not admin_ids:
                stats["rules_nodata"] += 1
                continue

            model_rules = rules_by_model.get(model_name, [])
            acl_read = self._expect_access_ok(tester, model_name, "read")
            so, user_ids = self._rpc_safe(
                tester, model_name, "search", [[]], {"limit": self.rule_sample_size}
            )

            if acl_read and so == "denied":
                stats["rules_fail"] += 1
                self._record_break(
                    role_name,
                    role_id,
                    model_name,
                    "read",
                    "record_rule",
                    f"read ACL OK but search denied (admin has {len(admin_ids)} record(s))",
                    model_rules,
                )
                continue
            if so == "skip":
                stats["rules_skip"] += 1
                continue

            _, admin_count = self._rpc_safe(
                self.admin, model_name, "search_count", [[]]
            )
            _, user_count = self._rpc_safe(tester, model_name, "search_count", [[]])
            if (
                admin_count is not None
                and user_count is not None
                and admin_count > 0
                and user_count < admin_count
            ):
                stats["rules_filtered"] += 1

            allowed_reads = blocked_reads = 0
            for rec_id in admin_ids:
                ro, _ = self._rpc_safe(tester, model_name, "read", [[rec_id], ["id"]])
                if ro == "ok":
                    allowed_reads += 1
                elif ro == "denied":
                    blocked_reads += 1

            if blocked_reads == len(admin_ids) and allowed_reads == 0:
                stats["rules_blocked_all"] += 1
            elif allowed_reads > 0:
                stats["rules_pass"] += 1

            if perms.get("write") and self._expect_access_ok(tester, model_name, "write"):
                probe_id = user_ids[0] if user_ids else None
                if probe_id:
                    wo, _ = self._rpc_safe(
                        tester, model_name, "write", [[probe_id], {}]
                    )
                    if wo == "denied":
                        stats["rules_fail"] += 1
                        self._record_break(
                            role_name,
                            role_id,
                            model_name,
                            "write",
                            "record_rule",
                            f"write denied on visible record {probe_id}",
                            model_rules,
                        )
                    elif wo == "ok":
                        stats["rules_pass"] += 1
                else:
                    stats["rules_skip"] += 1

        self.passed += stats.get("rules_pass", 0)
        self.skipped += stats.get("rules_skip", 0)
        return dict(stats)

    def _cleanup_created_records(self) -> None:
        for model_name, ids in list(self._created_record_ids.items()):
            if not ids:
                continue
            try:
                self.admin.unlink(model_name, ids)
            except RuntimeError as exc:
                print(f"  [WARN] cleanup {model_name} {ids}: {exc}")
        self._created_record_ids.clear()

    @staticmethod
    def _format_crud_stats(stats: dict[str, int]) -> str:
        parts = []
        for op in ("read", "write", "create", "unlink"):
            p = stats.get(f"{op}_pass", 0)
            f = stats.get(f"{op}_fail", 0)
            if p or f:
                parts.append(f"{op}:{p}/{f}")
        return " ".join(parts) if parts else "n/a"

    @staticmethod
    def _format_rule_stats(stats: dict[str, int]) -> str:
        return (
            f"pass={stats.get('rules_pass', 0)} "
            f"fail={stats.get('rules_fail', 0)} "
            f"filtered={stats.get('rules_filtered', 0)}"
        )

    def _test_smoke_models_as_user(
        self,
        tester: OdooRPCClient,
        model_names: list[str],
        expect_read: bool,
        role_name: str,
        role_id: int,
        rules_by_model: dict[str, list[str]],
    ) -> tuple[int, int, int]:
        passed = failed = skipped = 0
        for model_name in model_names:
            outcome = self._search_result(tester, model_name)
            if outcome == "ok":
                passed += 1
            elif outcome == "denied":
                if expect_read:
                    failed += 1
                    self._record_break(
                        role_name,
                        role_id,
                        model_name,
                        "read",
                        "smoke",
                        "search denied but read expected from ACL",
                        rules_by_model.get(model_name),
                    )
            else:
                skipped += 1
        self.passed += passed
        self.skipped += skipped
        return passed, failed, skipped

    def _print_break_report(self) -> None:
        print("\n" + "=" * 100)
        print("BREAK REPORT — BY ROLE")
        print("=" * 100)
        if not self.all_breaks:
            print("No breaks detected.")
            return

        for role_name in sorted(self.breaks_by_role):
            breaks = self.breaks_by_role[role_name]
            print(f"\n## {role_name} ({len(breaks)} break(s))")
            for b in breaks:
                rules = f" | rules: {', '.join(b['rules'][:3])}" if b.get("rules") else ""
                print(
                    f"  - {b['model']}.{b['operation']} [{b.get('category', b['layer'])}] "
                    f"{b['message']}{rules}"
                )

        print("\n" + "=" * 100)
        print("BREAK REPORT — BY MODEL")
        print("=" * 100)
        for model_name in sorted(self.breaks_by_model):
            breaks = self.breaks_by_model[model_name]
            roles = sorted({b["role"] for b in breaks})
            print(f"\n## {model_name} ({len(breaks)} break(s), roles: {', '.join(roles)})")
            for b in breaks:
                print(
                    f"  - {b['role']}.{b['operation']} "
                    f"[{b.get('category', b['layer'])}] {b['message']}"
                )

    def _write_report_file(self, roles_tested: int) -> None:
        if not self.report_file:
            return
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "database": self.admin.db,
            "url": self.admin.url,
            "roles_tested": roles_tested,
            "violates_access_rules": self._any_access_violation,
            "total_breaks": len(self.all_breaks),
            "passed_checks": self.passed,
            "failed_checks": self.failed,
            "skipped_checks": self.skipped,
            "breaks": self.all_breaks,
            "breaks_by_role": dict(self.breaks_by_role),
            "breaks_by_model": dict(self.breaks_by_model),
            "role_summary": self.role_results,
            "access_verdicts": {
                name: res.get("access_verdict", {})
                for name, res in self.role_results.items()
            },
        }
        path = Path(self.report_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == ".csv":
            with path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(
                    fh,
                    fieldnames=[
                        "role",
                        "role_id",
                        "model",
                        "operation",
                        "layer",
                        "category",
                        "message",
                        "rules",
                    ],
                )
                writer.writeheader()
                for row in self.all_breaks:
                    writer.writerow({**row, "rules": "|".join(row.get("rules") or [])})
        else:
            path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\nReport written to {path}")

    def _test_role(self, role: dict) -> dict:
        role_id = role["id"]
        role_name = role["name"]
        print(f"\n--- Role: {role_name} (id={role_id}, xml_id={role['xml_id']}) ---")

        result = {
            "name": role_name,
            "id": role_id,
            "xml_id": role["xml_id"],
            "groups_ok": False,
            "access_pass": 0,
            "access_fail": 0,
            "smoke_pass": 0,
            "smoke_fail": 0,
            "smoke_skip": 0,
            "crud_stats": {},
            "rules_stats": {},
            "crud_fail": 0,
            "rules_fail": 0,
            "break_count": 0,
            "models_tested": 0,
            "access_rules_count": 0,
            "record_rules_count": 0,
            "smoke_mode": self.smoke_mode,
            "status": "FAIL",
            "security_violations": 0,
        }

        try:
            self._assign_single_role(role_id)
        except RuntimeError as exc:
            print(f"  [FAIL] Could not assign role: {exc}")
            self.failed += 1
            result["status"] = "ERROR"
            return result

        result["groups_ok"] = self._verify_groups_synced(role_id)

        tester = OdooRPCClient(
            self.admin.url,
            self.admin.db,
            self.test_login,
            self.test_password,
            self.admin.protocol,
        )
        try:
            tester.authenticate()
        except RuntimeError as exc:
            print(f"  [FAIL] Test user authentication: {exc}")
            self.failed += 1
            result["status"] = "ERROR"
            return result

        access_rules = self._get_role_access_rules(role_id)
        record_rules = self._get_role_record_rules(role_id)
        self._role_model_cache = self._model_technical_name_cache(
            access_rules, record_rules
        )
        rules_by_model = self._rules_by_model(record_rules, self._role_model_cache)
        model_perms = self._build_model_permissions_from_access_and_rules(
            access_rules, record_rules
        )
        test_models, model_source = self._resolve_test_models(access_rules, record_rules)

        result["access_rules_count"] = len(access_rules)
        result["record_rules_count"] = len(record_rules)
        result["models_tested"] = len(test_models)

        print(
            f"  Dynamic scope: {len(access_rules)} ACL row(s), "
            f"{len(record_rules)} rule(s), {len(test_models)} model(s) [{model_source}]"
        )

        if access_rules:
            ap, af = self._test_access_rules_as_user(
                tester, access_rules, role_name, role_id, rules_by_model
            )
            result["access_pass"] = ap
            result["access_fail"] = af
            print(f"  ACL check_access_rights: {ap} passed, {af} failed")
        else:
            self._skip("No ir.model.access for role groups", role_name)

        if model_perms:
            result["security_violations"] = self._test_unexpected_access(
                tester, model_perms, role_name, role_id, rules_by_model
            )

        try:
            if not self.skip_crud and model_perms:
                crud_stats = self._test_crud_operations(
                    tester, model_perms, role_name, role_id, rules_by_model
                )
                result["crud_stats"] = crud_stats
                result["crud_fail"] = sum(
                    crud_stats.get(f"{op}_fail", 0)
                    for op in ("read", "write", "create", "unlink")
                )
                print(f"  CRUD operations: {self._format_crud_stats(crud_stats)}")
            elif not self.skip_crud:
                self._skip("CRUD tests", "no model permissions")

            if not self.skip_rules and model_perms:
                rules_stats = self._test_record_rules(
                    tester, model_perms, role_name, role_id, rules_by_model
                )
                result["rules_stats"] = rules_stats
                result["rules_fail"] = rules_stats.get("rules_fail", 0)
                print(f"  Record rules (existing data): {self._format_rule_stats(rules_stats)}")
            elif not self.skip_rules:
                self._skip("Record rule tests", "no model permissions")

            if not self.skip_smoke:
                expect_read = self.smoke_mode in ("access", "fixed", "all")
                smoke_models = test_models if self.smoke_mode != "fixed" else SMOKE_MODELS_FIXED
                if smoke_models:
                    sp, sf, ss = self._test_smoke_models_as_user(
                        tester,
                        smoke_models,
                        expect_read=expect_read,
                        role_name=role_name,
                        role_id=role_id,
                        rules_by_model=rules_by_model,
                    )
                    result["smoke_pass"] = sp
                    result["smoke_fail"] = sf
                    result["smoke_skip"] = ss
                    print(
                        f"  Smoke search: {sp} passed, {sf} failed, {ss} skipped "
                        f"(of {len(smoke_models)} model(s))"
                    )
                else:
                    self._skip("Smoke tests", "no models in dynamic scope")
        finally:
            self._cleanup_created_records()

        result["break_count"] = len(self.breaks_by_role.get(role_name, []))
        result["access_verdict"] = self._compute_role_verdict(role_name)
        verdict = result["access_verdict"]
        if result.get("status") != "ERROR":
            if verdict["violates_access_rules"]:
                result["status"] = "VIOLATES"
            elif verdict["verdict"] == "GAPS":
                result["status"] = "GAPS"
            elif result["groups_ok"]:
                result["status"] = "PASS"
        print(f"  Access verdict: {verdict['verdict']} — {verdict['summary']}")
        return result

    def run(self) -> bool:
        print("=" * 80)
        print("Access Rights Management — Role RPC Test (Odoo 19)")
        print(f"Module : {MODULE_NAME}")
        print(f"Protocol: {self.admin.protocol.upper()} | DB: {self.admin.db} | URL: {self.admin.url}")
        print(f"Roles XML: {ROLES_DATA_XML}")
        print("=" * 80)

        roles = resolve_roles(self.admin, self.role_defs, self.roles_from)
        if self.role_filter:
            wanted = {n.lower() for n in self.role_filter}
            roles = [r for r in roles if r["name"].lower() in wanted]
            print(f"Filtered to {len(roles)} role(s): {', '.join(r['name'] for r in roles)}")
        if not roles:
            print("ERROR: No roles found. Install base_user_role and load roles_data.xml.")
            return False

        ir_models = self._load_ir_models()
        self._rpc_disabled_models = self._load_rpc_disabled_models()
        if self._rpc_disabled_models:
            print(
                f"RPC-blocked models (rpc_helper): {len(self._rpc_disabled_models)} "
                f"(ACL breaks on these are classified as test noise)"
            )
        print(f"Found {len(roles)} role(s) | {len(ir_models)} model(s) in ir.model (dynamic)")
        print(
            f"Discovery: role groups → ir.model.access + ir.rule "
            f"(roles-from={self.roles_from})"
        )
        if not self.skip_crud:
            print("CRUD: read / write / create / unlink on every model in role scope")
        if not self.skip_rules:
            print(f"Record rules: admin samples {self.rule_sample_size} existing records/model")
        if self.allow_destructive:
            print("[WARN] --allow-destructive: unlink may delete real records!")

        self._ensure_test_user()
        assert self.test_user_id is not None
        print(f"Test user: {self.test_login} (id={self.test_user_id})")
        self._backup_role_lines()

        try:
            for role in roles:
                self.role_results[role["name"]] = self._test_role(role)
        finally:
            print("\n--- Restoring test user original roles ---")
            try:
                self._restore_role_lines()
                print("  Original roles restored.")
            except RuntimeError as exc:
                print(f"  [WARN] Could not restore roles: {exc}")

        # Summary table
        print("\n" + "=" * 80)
        print("ROLE SUMMARY")
        print("=" * 80)
        print(
            f"{'Role':<28} {'Verdict':<9} {'Violates':<9} {'Breaks':<7} {'Models':<8} "
            f"{'ACL':<8}"
        )
        print("-" * 80)
        for name, res in self.role_results.items():
            access = f"{res['access_pass']}/{res['access_fail']}"
            av = res.get("access_verdict", {})
            verdict = av.get("verdict", res["status"])
            violates = "YES" if av.get("violates_access_rules") else "NO"
            print(
                f"{name:<28} {verdict:<9} {violates:<9} {res.get('break_count', 0):<7} "
                f"{res.get('models_tested', 0):<8} {access:<8}"
            )

        self._print_break_report()
        self._print_overall_verdict()
        self._write_report_file(len(roles))

        print("=" * 80)
        print(
            f"Total: {self.passed} passed, {self.failed} failed (breaks), "
            f"{self.skipped} skipped across {len(self.role_results)} role(s)"
        )
        print(f"Unique breaks (raw): {len(self.all_breaks)}")
        print("=" * 80)
        return not self._any_access_violation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RPC role access test for access_rights_management (Odoo 19)",
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--user", default=DEFAULT_USER, help="Admin username")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Admin password")
    parser.add_argument(
        "--protocol",
        choices=["jsonrpc", "xmlrpc"],
        default=DEFAULT_PROTOCOL,
    )
    parser.add_argument(
        "--test-login",
        default=TEST_USER_LOGIN,
        help=f"Test user login (default: {TEST_USER_LOGIN})",
    )
    parser.add_argument(
        "--test-password",
        default=TEST_USER_PASSWORD,
        help="Password set on the test user",
    )
    parser.add_argument(
        "--roles-xml",
        default=str(ROLES_DATA_XML),
        help="Path to data/roles_data.xml",
    )
    parser.add_argument(
        "--roles",
        nargs="+",
        metavar="NAME",
        help="Test only these role names (e.g. --roles President CFO). Default: all roles",
    )
    parser.add_argument(
        "--roles-from",
        choices=["xml", "db"],
        default="xml",
        help=(
            "Role source: 'xml' = all roles from data/roles_data.xml (default); "
            "'db' = every res.users.role in the database"
        ),
    )
    parser.add_argument(
        "--report-file",
        default="",
        help="Write full break report to JSON or CSV path (e.g. /tmp/breaks.json)",
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip smoke search tests entirely",
    )
    parser.add_argument(
        "--smoke-mode",
        choices=["access", "all", "fixed"],
        default="access",
        help=(
            "Model scope: 'access' = ACL+rules for role groups (default); "
            "'all' = entire ir.model registry; 'fixed' = legacy static list"
        ),
    )
    parser.add_argument(
        "--skip-crud",
        action="store_true",
        help="Skip operational CRUD tests (read/write/create/unlink)",
    )
    parser.add_argument(
        "--skip-rules",
        action="store_true",
        help="Skip record-rule probes on existing data",
    )
    parser.add_argument(
        "--rule-sample-size",
        type=int,
        default=5,
        help="How many existing records admin samples per model for rule tests (default: 5)",
    )
    parser.add_argument(
        "--allow-destructive",
        action="store_true",
        help="Allow unlink probes on existing visible records (NOT for production)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    role_defs = parse_roles_from_xml(Path(args.roles_xml))

    admin = OdooRPCClient(args.url, args.db, args.user, args.password, args.protocol)
    try:
        uid = admin.authenticate()
        print(f"Admin authenticated uid={uid}")
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    runner = AccessRightsRoleRPCTest(
        admin=admin,
        test_login=args.test_login,
        test_password=args.test_password,
        role_defs=role_defs,
        roles_from=args.roles_from,
        role_filter=args.roles,
        report_file=args.report_file or None,
        skip_smoke=args.skip_smoke,
        smoke_mode=args.smoke_mode,
        skip_crud=args.skip_crud,
        skip_rules=args.skip_rules,
        rule_sample_size=args.rule_sample_size,
        allow_destructive=args.allow_destructive,
        verbose=args.verbose,
    )
    success = runner.run()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
