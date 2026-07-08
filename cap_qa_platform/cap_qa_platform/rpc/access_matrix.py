"""Load ir.model.access + ir.rule expectations for a role (no assumptions)."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from cap_qa_platform.rpc.client import OdooRPCClient, m2o_id
from cap_qa_platform.rpc.errors import is_access_error

PERM_FIELDS = ("perm_read", "perm_write", "perm_create", "perm_unlink")
PERM_TO_OP = {
    "perm_read": "read",
    "perm_write": "write",
    "perm_create": "create",
    "perm_unlink": "unlink",
}

BREAK_CATEGORY_SECURITY = "security_violation"
BREAK_CATEGORY_CONFIG_GAP = "config_gap"
BREAK_CATEGORY_RECORD_SCOPE = "record_rule_scope"
BREAK_CATEGORY_OTHER = "other"


def _group_ids_for_role(admin: OdooRPCClient, role_id: int) -> set[int]:
    role_data = admin.read(
        "res.users.role",
        [role_id],
        ["all_implied_ids", "implied_ids"],
    )[0]
    return set(role_data.get("all_implied_ids") or role_data.get("implied_ids") or [])


def get_role_access_rules(admin: OdooRPCClient, role_id: int) -> list[dict]:
    group_ids = _group_ids_for_role(admin, role_id)
    if not group_ids:
        return []
    access_ids = admin.search(
        "ir.model.access", [("group_id", "in", list(group_ids))]
    )
    if not access_ids:
        return []
    return admin.read(
        "ir.model.access",
        access_ids,
        ["name", "model_id", "group_id", *PERM_FIELDS],
    )


def get_role_record_rules(admin: OdooRPCClient, role_id: int) -> list[dict]:
    group_ids = _group_ids_for_role(admin, role_id)
    if not group_ids:
        return []
    rule_ids = admin.search(
        "ir.rule",
        [("groups", "in", list(group_ids)), ("active", "=", True)],
    )
    if not rule_ids:
        return []
    return admin.read(
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


def model_technical_name_cache(
    admin: OdooRPCClient, *rule_lists: list[dict]
) -> dict[int, str]:
    ir_model_ids: set[int] = set()
    for rules in rule_lists:
        for rule in rules:
            mid = rule.get("model_id")
            if mid:
                ir_model_ids.add(m2o_id(mid) or 0)
    ir_model_ids.discard(0)
    if not ir_model_ids:
        return {}
    rows = admin.read("ir.model", list(ir_model_ids), ["model", "transient"])
    return {r["id"]: r["model"] for r in rows if not r.get("transient")}


def rule_model_technical(rule: dict, model_cache: dict[int, str]) -> str | None:
    mid = m2o_id(rule.get("model_id"))
    if not mid:
        return None
    return model_cache.get(mid)


def rules_by_model(
    record_rules: list[dict], model_cache: dict[int, str]
) -> dict[str, list[str]]:
    by_model: dict[str, list[str]] = defaultdict(list)
    for rule in record_rules:
        technical = rule_model_technical(rule, model_cache)
        if technical:
            by_model[technical].append(rule.get("name") or "?")
    return dict(by_model)


def build_model_permissions(
    access_rules: list[dict],
    record_rules: list[dict],
    model_cache: dict[int, str],
) -> dict[str, dict[str, bool]]:
    perms: dict[str, dict[str, bool]] = defaultdict(
        lambda: {"read": False, "write": False, "create": False, "unlink": False}
    )
    for rule in access_rules:
        model_name = rule_model_technical(rule, model_cache)
        if not model_name:
            continue
        for perm_field, op in PERM_TO_OP.items():
            if rule.get(perm_field):
                perms[model_name][op] = True
    for rule in record_rules:
        model_name = rule_model_technical(rule, model_cache)
        if not model_name:
            continue
        if rule.get("perm_read"):
            perms[model_name]["read"] = True
        if rule.get("perm_write"):
            perms[model_name]["write"] = True
        if rule.get("perm_create"):
            perms[model_name]["create"] = True
        if rule.get("perm_unlink"):
            perms[model_name]["unlink"] = True
    return dict(perms)


def acl_rows_for_model(access_rules: list[dict], model: str, model_cache: dict[int, str]) -> list[str]:
    names: list[str] = []
    for rule in access_rules:
        if rule_model_technical(rule, model_cache) == model:
            names.append(rule.get("name") or "?")
    return names


def rpc_search_outcome(tester: OdooRPCClient, model: str) -> str:
    try:
        tester.execute_kw(model, "search", [[]], {"limit": 1})
        return "ok"
    except Exception as exc:
        if is_access_error(exc):
            return "denied"
        return "skip"


def rpc_check_access(tester: OdooRPCClient, model: str, operation: str = "read") -> str:
    try:
        tester.execute_kw(
            model,
            "check_access_rights",
            [operation],
            {"raise_exception": True},
        )
        return "allowed"
    except Exception as exc:
        if is_access_error(exc):
            return "denied"
        return "skip"


def compute_role_verdict(breaks: list[dict[str, Any]]) -> dict[str, Any]:
    """Same semantics as access_rights RPC runner (_compute_role_verdict)."""
    counts: dict[str, int] = defaultdict(int)
    for entry in breaks:
        counts[entry.get("category", BREAK_CATEGORY_OTHER)] += 1

    security = counts[BREAK_CATEGORY_SECURITY]
    config_gap = counts[BREAK_CATEGORY_CONFIG_GAP]
    record_scope = counts[BREAK_CATEGORY_RECORD_SCOPE]

    if security > 0:
        verdict = "VIOLATES"
        summary = (
            f"VIOLATES access rules — {security} over-access issue(s) "
            f"(effective access where ir.model.access / ir.rule do not grant read)"
        )
    elif config_gap > 0:
        verdict = "GAPS"
        summary = (
            f"Does NOT violate rules, but {config_gap} configuration gap(s) "
            f"(ACL/rules grant read but UI or RPC denies)"
        )
    elif breaks:
        verdict = "CLEAN"
        summary = f"Findings only in record-rule scope ({record_scope}) or informational"
    else:
        verdict = "CLEAN"
        summary = "ACL + record rules align with UI and RPC for smoke models"

    return {
        "verdict": verdict,
        "summary": summary,
        "security_violations": security,
        "config_gaps": config_gap,
        "record_scope": record_scope,
        "break_count": len(breaks),
    }


class RoleAccessContext:
    """ACL + record rules loaded from DB for one role."""

    def __init__(
        self,
        admin: OdooRPCClient,
        role_id: int,
        role_name: str,
    ):
        self.role_id = role_id
        self.role_name = role_name
        self.access_rules = get_role_access_rules(admin, role_id)
        self.record_rules = get_role_record_rules(admin, role_id)
        self.model_cache = model_technical_name_cache(
            admin, self.access_rules, self.record_rules
        )
        self.rules_by_model = rules_by_model(self.record_rules, self.model_cache)
        self.model_perms = build_model_permissions(
            self.access_rules, self.record_rules, self.model_cache
        )

    def acl_grants_read(self, model: str) -> bool:
        return bool(self.model_perms.get(model, {}).get("read"))

    def acl_rule_names(self, model: str) -> list[str]:
        return acl_rows_for_model(self.access_rules, model, self.model_cache)

    def record_rule_names(self, model: str) -> list[str]:
        return self.rules_by_model.get(model, [])
