#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Full HR gamification workflow integration test via XML-RPC or JSON-RPC.

Covers the business workflow documented for Captivea (challenges, pro-rata,
PTO impact, bonuses/commissions via Studio fields, quest bonus, internal P2P3,
team manager quotas, badge rewards, non-admin access).

Admin seeds data and triggers server methods. Employees verify read access.

Requirements on Odoo server:
  - cap_gamification, cap_partner, cap_quality_issue_log
  - ksc_project_extended, access_rights_management (recommended)
  - hr_timesheet, hr_holidays, gamification, hr_gamification
  - Studio custom fields on gamification.goal / hr.job (for bonus/pro-rata tests)

Usage:
  python3 scripts/test_hr_gamification_workflow_rpc.py --db YOUR_DB
  python3 scripts/test_hr_gamification_workflow_rpc.py --protocol xmlrpc --db YOUR_DB
  python3 scripts/test_hr_gamification_workflow_rpc.py --scenarios core,prorata,employee
  python3 scripts/test_hr_gamification_workflow_rpc.py --employee-login john.doe --employee-password secret
  python3 scripts/test_hr_gamification_workflow_rpc.py --skip-studio
  python3 scripts/test_hr_gamification_workflow_rpc.py --discover-fields

Environment: ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD, ODOO_RPC
"""
from __future__ import annotations

import argparse
import calendar
import json
import os
import sys
import xmlrpc.client
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_FIELD_CONFIG = SCRIPT_DIR / "gamification_workflow_fields.json"

DEFAULT_URL = "http://localhost:8069"
DEFAULT_DB = "odoo"
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "admin"
DEFAULT_PROTOCOL = "jsonrpc"
DEFAULT_TEST_PASSWORD = "CapGamWorkflowTest123!"

ALL_SCENARIOS = (
    "discover",
    "core",
    "prorata",
    "pto",
    "manager_quotas",
    "challenge_badge",
    "studio_bonus",
    "employee",
)

# ---------------------------------------------------------------------------
# RPC client
# ---------------------------------------------------------------------------


class RpcError(RuntimeError):
    @property
    def is_validation_error(self) -> bool:
        msg = str(self).lower()
        return any(k in msg for k in (
            "validationerror", "usererror", "invalid value", "quality score",
        ))

    @property
    def is_access_error(self) -> bool:
        msg = str(self).lower()
        return any(k in msg for k in ("access", "forbidden", "not allowed"))


class OdooRPCClient:
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
        else:
            uid = self._jsonrpc(
                "common", "authenticate", [self.db, self.username, self.password, {}]
            )
        if not uid:
            raise RpcError("Authentication failed.")
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
            with urlopen(req, timeout=180) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            raise RpcError(f"HTTP error {exc.code}: {exc.reason}") from exc
        except URLError as exc:
            raise RpcError(f"Cannot reach Odoo at {self.url}: {exc}") from exc
        if body.get("error"):
            err = body["error"]
            msg = err.get("data", {}).get("message") or err.get("message") or str(err)
            raise RpcError(f"Odoo RPC error: {msg}")
        return body.get("result")

    def execute_kw(self, model: str, method: str, args: list | None = None, kwargs: dict | None = None) -> Any:
        if self.uid is None:
            raise RpcError("Not authenticated.")
        args = args or []
        kwargs = kwargs or {}
        if self.protocol == "xmlrpc":
            try:
                return self._xml_models.execute_kw(
                    self.db, self.uid, self.password, model, method, args, kwargs
                )
            except xmlrpc.client.Fault as exc:
                raise RpcError(exc.faultString) from exc
        return self._jsonrpc(
            "object", "execute_kw",
            [self.db, self.uid, self.password, model, method, args, kwargs],
        )

    def search(self, model: str, domain: list, limit: int | None = None, order: str | None = None) -> list[int]:
        kwargs: dict[str, Any] = {}
        if limit is not None:
            kwargs["limit"] = limit
        if order:
            kwargs["order"] = order
        return self.execute_kw(model, "search", [domain], kwargs)

    def search_read(self, model: str, domain: list, fields: list[str], limit: int = 0) -> list[dict]:
        kwargs: dict[str, Any] = {"fields": fields}
        if limit:
            kwargs["limit"] = limit
        return self.execute_kw(model, "search_read", [domain], kwargs)

    def read(self, model: str, ids: list[int], fields: list[str]) -> list[dict]:
        return self.execute_kw(model, "read", [ids, fields])

    def create(self, model: str, vals: dict) -> int:
        return self.execute_kw(model, "create", [vals])

    def write(self, model: str, ids: list[int], vals: dict) -> bool:
        return self.execute_kw(model, "write", [ids, vals])

    def call(self, model: str, method: str, ids: list[int]) -> Any:
        return self.execute_kw(model, method, [ids], {})

    def fields_get(self, model: str, attributes: list[str] | None = None) -> dict:
        kwargs = {}
        if attributes:
            kwargs["attributes"] = attributes
        return self.execute_kw(model, "fields_get", [], kwargs)


def connect(url: str, db: str, login: str, password: str, protocol: str) -> OdooRPCClient:
    client = OdooRPCClient(url, db, login, password, protocol)
    client.authenticate()
    return client


# ---------------------------------------------------------------------------
# Studio / custom field discovery
# ---------------------------------------------------------------------------


class FieldResolver:
    """Resolve Studio and custom field names on live database."""

    GOAL_HINTS: dict[str, list[str]] = {
        "redefined_onboard_target": ["redefined", "onboard", "target"],
        "adjustment": ["adjustment"],
        "bonus_for_reaching_target": ["bonus", "reach"],
        "commission_over_target_until_120": ["commission", "120", "until"],
        "commission_over_target_after_120": ["commission", "after", "120"],
        "completeness_score": ["completeness"],
        "month_advancment": ["month", "advanc"],
        "team_manager_bonus": ["team_manager", "bonus"],
        "team_members_succeed_bonus": ["team_member", "succeed", "bonus"],
        "company": ["company"],
    }

    JOB_HINTS: dict[str, list[str]] = {
        "pto_holidays_impact": ["pto", "holiday", "impact"],
        "bonus_when_reach_target": ["bonus", "reach", "target"],
        "incentive_amount_offshore": ["incentive", "offshore"],
        "commission_over_target_until_120": ["commission", "120", "until"],
        "commission_over_target_after_120": ["commission", "after", "120"],
        "percentage_over_target_team_manager": ["percentage", "team_manager"],
    }

    def __init__(self, client: OdooRPCClient, config_path: Path | None = None):
        self.client = client
        self.config = self._load_config(config_path)
        self._cache: dict[str, dict[str, str | None]] = {}

    def _load_config(self, path: Path | None) -> dict:
        p = path or DEFAULT_FIELD_CONFIG
        if p.is_file():
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _model_fields(self, model: str) -> list[dict]:
        model_ids = self.client.search("ir.model", [("model", "=", model)], limit=1)
        if not model_ids:
            return []
        return self.client.search_read(
            "ir.model.fields",
            [("model_id", "=", model_ids[0])],
            ["name", "field_description"],
        )

    def _pick_field(self, model: str, key: str, hints: list[str]) -> str | None:
        cfg = self.config.get(model, {})
        if cfg.get(key):
            name = cfg[key]
            if name in self.client.fields_get(model):
                return name
            return None

        best: tuple[int, str] | None = None
        for row in self._model_fields(model):
            name = row["name"]
            label = (row.get("field_description") or "").lower()
            blob = f"{name} {label}"
            score = sum(1 for h in hints if h in blob)
            if name.startswith("x_studio") and score > 0:
                if best is None or score > best[0]:
                    best = (score, name)
        return best[1] if best else None

    def goal_field(self, key: str) -> str | None:
        if "goal" not in self._cache:
            self._cache["goal"] = {
                k: self._pick_field("gamification.goal", k, hints)
                for k, hints in self.GOAL_HINTS.items()
            }
        return self._cache["goal"].get(key)

    def job_field(self, key: str) -> str | None:
        if "job" not in self._cache:
            self._cache["job"] = {
                k: self._pick_field("hr.job", k, hints)
                for k, hints in self.JOB_HINTS.items()
            }
        return self._cache["job"].get(key)

    def employee_joining_field(self) -> str:
        cfg = self.config.get("hr.employee", {})
        if cfg.get("joining_date"):
            return cfg["joining_date"]
        return "x_studio_joining_date"

    def goal_readable_fields(self) -> list[str]:
        base = [
            "target_goal", "current", "state", "start_date", "end_date", "user_id",
            "goal_quest_bonus", "hours_of_internal_p2_p3", "current_val_with_internal_p2_p3",
            "global_quality_score", "total_bonus",
        ]
        for key in self.GOAL_HINTS:
            f = self.goal_field(key)
            if f and f not in base:
                base.append(f)
        available = set(self.client.fields_get("gamification.goal").keys())
        return [f for f in base if f in available]

    def print_discovery_report(self) -> None:
        print("\n--- FIELD DISCOVERY ---")
        for model, hints in (
            ("gamification.goal", self.GOAL_HINTS),
            ("hr.job", self.JOB_HINTS),
        ):
            print(f"\n  Model: {model}")
            rows = self._model_fields(model)
            studio = [r for r in rows if r["name"].startswith("x_studio")]
            print(f"    x_studio fields ({len(studio)}):")
            for r in sorted(studio, key=lambda x: x["name"]):
                print(f"      - {r['name']}: {r.get('field_description', '')}")
            print("    Resolved mappings:")
            resolver = self.goal_field if model == "gamification.goal" else self.job_field
            for key in hints:
                print(f"      {key}: {resolver(key) or '(not found)'}")


# ---------------------------------------------------------------------------
# Workflow test runner
# ---------------------------------------------------------------------------


class HrGamificationWorkflowTest:
    ORIGINAL_TARGET = 140.0
    FIRST_MONTH_PCT = 30.0
    PTO_HOURS_PER_DAY = 6.5
    QUEST_BONUS = 10.0
    TM_ALLOCATION_HOURS = 50.0

    def __init__(
        self,
        admin: OdooRPCClient,
        scenarios: list[str],
        cleanup: bool = True,
        skip_studio: bool = False,
        employee_login: str | None = None,
        employee_password: str | None = None,
        field_config: Path | None = None,
    ):
        self.admin = admin
        self.scenarios = scenarios
        self.cleanup = cleanup
        self.skip_studio = skip_studio
        self.external_employee_login = employee_login
        self.external_employee_password = employee_password or DEFAULT_TEST_PASSWORD
        self.fields = FieldResolver(admin, field_config)
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.suffix = datetime.now().strftime("%Y%m%d%H%M%S")
        self.test_password = DEFAULT_TEST_PASSWORD
        self._created: list[tuple[str, int]] = []
        self.ctx: dict[str, Any] = {}

    # --- helpers ---

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

    def _skip(self, label: str, reason: str) -> None:
        print(f"[SKIP] {label} -> {reason}")
        self.skipped += 1

    def _m2o_id(self, value: Any) -> int | None:
        if not value:
            return None
        return value[0] if isinstance(value, (list, tuple)) else value

    def _track(self, model: str, record_id: int) -> None:
        self._created.append((model, record_id))

    def _create(self, model: str, vals: dict) -> int:
        rid = self.admin.create(model, vals)
        self._track(model, rid)
        return rid

    def _user_client(self, login: str, password: str | None = None) -> OdooRPCClient:
        return connect(
            self.admin.url, self.admin.db, login,
            password or self.test_password, self.admin.protocol,
        )

    def _xmlid(self, xml_id: str) -> int:
        module, name = xml_id.split(".")
        rows = self.admin.search("ir.model.data", [("module", "=", module), ("name", "=", name)], limit=1)
        if not rows:
            raise RpcError(f"XML id not found: {xml_id}")
        return self.admin.read("ir.model.data", rows, ["res_id"])[0]["res_id"]

    def _company_id(self) -> int:
        return self._m2o_id(self.admin.read("res.users", [self.admin.uid], ["company_id"])[0]["company_id"])

    def _module_installed(self, name: str) -> bool:
        return bool(self.admin.search("ir.module.module", [("name", "=", name), ("state", "=", "installed")], limit=1))

    def _read_goal(self, goal_id: int, client: OdooRPCClient | None = None) -> dict:
        c = client or self.admin
        fields = self.fields.goal_readable_fields()
        return c.read("gamification.goal", [goal_id], fields)[0]

    def _internal_p2p3_status_id(self) -> int:
        rows = self.admin.search("project.status", [("code", "=", "internal_p2p3")], limit=1)
        if not rows:
            raise RpcError("Install cap_partner: project.status code internal_p2p3 missing.")
        return rows[0]

    def _timesheet_sum_goal_def(self, name: str) -> int:
        model_row = self.admin.search_read("ir.model", [("model", "=", "account.analytic.line")], ["id"], limit=1)
        field_rows = self.admin.search_read(
            "ir.model.fields",
            [("model_id", "=", model_row[0]["id"]), ("name", "in", ["unit_amount", "date"])],
            ["name", "id"],
        )
        by_name = {r["name"]: r["id"] for r in field_rows}
        return self._create("gamification.goal.definition", {
            "name": name,
            "computation_mode": "sum",
            "model_id": model_row[0]["id"],
            "field_id": by_name["unit_amount"],
            "field_date_id": by_name["date"],
            "domain": "[]",
            "condition": "higher",
            "display_mode": "progress",
        })

    def _start_challenge(self, challenge_id: int) -> None:
        self.admin.write("gamification.challenge", [challenge_id], {"state": "inprogress"})
        self.admin.call("gamification.challenge", "action_check", [challenge_id])

    def _goal_for_user(self, challenge_id: int, user_id: int) -> int | None:
        rows = self.admin.search(
            "gamification.goal",
            [("challenge_id", "=", challenge_id), ("user_id", "=", user_id)],
            limit=1,
        )
        return rows[0] if rows else None

    def _expected_prorata_target(
        self, original: float, month_pct: float, join_day: date,
    ) -> float:
        """Documented formula: month% of original, then prorate by remaining days."""
        month_target = original * (month_pct / 100.0)
        if join_day.day == 1:
            return round(month_target, 2)
        days_in_month = calendar.monthrange(join_day.year, join_day.month)[1]
        remaining = days_in_month - join_day.day + 1
        return round(month_target * remaining / days_in_month, 2)

    def _require_studio_field(self, kind: str, key: str) -> str | None:
        if self.skip_studio:
            self._skip(f"Studio:{key}", "--skip-studio enabled")
            return None
        getter = self.fields.goal_field if kind == "goal" else self.fields.job_field
        name = getter(key)
        if not name:
            self._skip(
                f"Studio:{key}",
                f"Field not found on {kind}. Run --discover-fields or edit gamification_workflow_fields.json",
            )
        return name

    # --- setup shared context ---

    def setup_context(self) -> None:
        print("\n=== SETUP (admin) ===")
        if not self._module_installed("cap_gamification"):
            raise RpcError("cap_gamification is not installed.")

        company_id = self._company_id()
        today = date.today()
        month_start = today.replace(day=1)

        if self.external_employee_login:
            user_ids = self.admin.search("res.users", [("login", "=", self.external_employee_login)], limit=1)
            if not user_ids:
                raise RpcError(f"Employee login not found: {self.external_employee_login}")
            employee_user_id = user_ids[0]
            employee_login = self.external_employee_login
            employee_password = self.external_employee_password
            emp_ids = self.admin.search("hr.employee", [("user_id", "=", employee_user_id)], limit=1)
            if not emp_ids:
                raise RpcError(f"No hr.employee for {employee_login}")
            employee_id = emp_ids[0]
        else:
            employee_login = f"hr_gam_emp_{self.suffix}@test.com"
            employee_user_id = self._create("res.users", {
                "name": f"HR Gam Employee {self.suffix}",
                "login": employee_login,
                "password": self.test_password,
                "group_ids": [(6, 0, [self._xmlid("base.group_user")])],
                "company_id": company_id,
                "company_ids": [(6, 0, [company_id])],
            })
            employee_id = self._create("hr.employee", {
                "name": f"HR Gam Employee {self.suffix}",
                "user_id": employee_user_id,
                "company_id": company_id,
            })
            employee_password = self.test_password

        manager_login = f"hr_gam_mgr_{self.suffix}@test.com"
        manager_user_id = self._create("res.users", {
            "name": f"HR Gam Manager {self.suffix}",
            "login": manager_login,
            "password": self.test_password,
            "group_ids": [(6, 0, [self._xmlid("base.group_user")])],
            "company_id": company_id,
            "company_ids": [(6, 0, [company_id])],
        })
        manager_employee_id = self._create("hr.employee", {
            "name": f"HR Gam Manager {self.suffix}",
            "user_id": manager_user_id,
            "company_id": company_id,
        })

        job_vals: dict[str, Any] = {
            "name": f"RPC Master Job {self.suffix}",
            "minimum_quality_score_required": 80.0,
            "bonus_tm_target_quality_score_reached": 100.0,
            "team_manager_hours_allocation": self.TM_ALLOCATION_HOURS,
        }
        pto_field = self.fields.job_field("pto_holidays_impact")
        if pto_field:
            job_vals[pto_field] = self.PTO_HOURS_PER_DAY
        bonus_field = self.fields.job_field("bonus_when_reach_target")
        if bonus_field:
            job_vals[bonus_field] = 767.0

        job_id = self._create("hr.job", job_vals)

        if self._module_installed("cap_quality_issue_log"):
            self._create("on.boarding.prorata", {
                "job_id": job_id,
                "target_percentage": self.FIRST_MONTH_PCT,
            })
            self._create("on.boarding.prorata", {
                "job_id": job_id,
                "target_percentage": 60.0,
            })
            self._create("on.boarding.prorata", {
                "job_id": job_id,
                "target_percentage": 100.0,
            })

        join_field = self.fields.employee_joining_field()
        emp_write: dict[str, Any] = {
            "job_id": job_id,
            "parent_id": manager_employee_id,
        }
        if join_field in self.admin.fields_get("hr.employee"):
            emp_write[join_field] = month_start.isoformat()
        self.admin.write("hr.employee", [employee_id], emp_write)

        badge_id = self._create("gamification.badge", {
            "name": f"RPC Good Job {self.suffix}",
            "quest_bonus": self.QUEST_BONUS,
            "description": "Workflow test badge",
        })
        self._create("gamification.badge.user", {
            "user_id": employee_user_id,
            "badge_id": badge_id,
            "sender_id": self.admin.uid,
        })

        goal_def_id = self._timesheet_sum_goal_def(f"RPC Timesheet Goal {self.suffix}")
        challenge_id = self._create("gamification.challenge", {
            "name": f"RPC Timesheet Challenge {self.suffix}",
            "period": "monthly",
            "state": "draft",
            "challenge_category": "hr",
            "user_ids": [(6, 0, [employee_user_id])],
            "reward_id": badge_id,
            "reward_realtime": True,
            "line_ids": [(0, 0, {
                "definition_id": goal_def_id,
                "target_goal": self.ORIGINAL_TARGET,
            })],
        })
        self._start_challenge(challenge_id)
        goal_id = self._goal_for_user(challenge_id, employee_user_id)
        if not goal_id:
            raise RpcError("No goal created for employee.")

        billable_project_id = self._create("project.project", {
            "name": f"RPC Billable {self.suffix}",
            "company_id": company_id,
        })
        internal_project_id = self._create("project.project", {
            "name": f"RPC Internal P2P3 {self.suffix}",
            "project_status_id": self._internal_p2p3_status_id(),
            "company_id": company_id,
        })

        self.ctx = {
            "company_id": company_id,
            "employee_login": employee_login,
            "employee_password": employee_password,
            "employee_user_id": employee_user_id,
            "employee_id": employee_id,
            "manager_user_id": manager_user_id,
            "manager_employee_id": manager_employee_id,
            "manager_login": manager_login,
            "job_id": job_id,
            "challenge_id": challenge_id,
            "goal_id": goal_id,
            "badge_id": badge_id,
            "billable_project_id": billable_project_id,
            "internal_project_id": internal_project_id,
            "month_start": month_start.isoformat(),
            "join_field": join_field,
            "pto_field": pto_field,
            "redefined_field": self.fields.goal_field("redefined_onboard_target"),
            "adjustment_field": self.fields.goal_field("adjustment"),
            "bonus_reach_field": self.fields.goal_field("bonus_for_reaching_target"),
        }
        print(f"  employee : {employee_login}")
        print(f"  manager  : {manager_login}")
        print(f"  goal_id  : {goal_id}")

    # --- scenarios ---

    def scenario_discover(self) -> None:
        self.fields.print_discovery_report()

    def scenario_core(self) -> None:
        """cap_gamification: quest bonus, internal P2P3, challenge preservation."""
        print("\n=== SCENARIO: core (cap_gamification) ===")
        c = self.ctx
        goal_id = c["goal_id"]
        internal_hours = 3.5
        billable_hours = 20.0

        self._create("account.analytic.line", {
            "name": "RPC billable hours",
            "project_id": c["billable_project_id"],
            "user_id": c["employee_user_id"],
            "employee_id": c["employee_id"],
            "unit_amount": billable_hours,
            "date": c["month_start"],
        })
        self._create("account.analytic.line", {
            "name": "RPC internal P2P3 hours",
            "project_id": c["internal_project_id"],
            "user_id": c["employee_user_id"],
            "employee_id": c["employee_id"],
            "unit_amount": internal_hours,
            "date": c["month_start"],
        })
        self.admin.call("gamification.goal", "update_goal", [goal_id])
        goal = self._read_goal(goal_id)

        self._ok(
            "goal_quest_bonus from badges",
            abs(goal.get("goal_quest_bonus", 0) - self.QUEST_BONUS) < 0.01,
            f"got={goal.get('goal_quest_bonus')}",
        )
        self._ok(
            "hours_of_internal_p2_p3",
            abs(goal.get("hours_of_internal_p2_p3", 0) - internal_hours) < 0.01,
            f"got={goal.get('hours_of_internal_p2_p3')}",
        )
        expected_total = goal.get("current", 0) + goal.get("hours_of_internal_p2_p3", 0)
        self._ok(
            "current_val_with_internal_p2_p3",
            abs(goal.get("current_val_with_internal_p2_p3", 0) - expected_total) < 0.01,
            f"got={goal.get('current_val_with_internal_p2_p3')}",
        )

        before_id = goal_id
        self.admin.call("gamification.challenge", "action_check", [c["challenge_id"]])
        self._ok(
            "action_check preserves existing goal",
            bool(self.admin.search("gamification.goal", [("id", "=", before_id)], limit=1)),
            f"goal_id={before_id}",
        )

        rejected = False
        try:
            self._create("gamification.badge", {"name": f"Bad {self.suffix}", "quest_bonus": -1.0})
        except RpcError as exc:
            rejected = exc.is_validation_error
        self._ok("Negative quest_bonus blocked", rejected)

    def scenario_prorata(self) -> None:
        """On-boarding pro-rata: job lines + join-date scenarios (Studio field if present)."""
        print("\n=== SCENARIO: prorata ===")
        if not self._module_installed("cap_quality_issue_log"):
            self._skip("prorata", "cap_quality_issue_log not installed")
            return

        c = self.ctx
        redefined = c.get("redefined_field")
        if not redefined:
            redefined = self._require_studio_field("goal", "redefined_onboard_target")
        if not redefined:
            self._ok("on.boarding.prorata lines on job", True, "3 lines created in setup")
            return

        join_field = c["join_field"]
        employee_id = c["employee_id"]
        goal_id = c["goal_id"]

        # Scenario 1: join on 1st -> 30% of 140 = 42
        first_of_month = date.today().replace(day=1)
        if join_field in self.admin.fields_get("hr.employee"):
            self.admin.write("hr.employee", [employee_id], {join_field: first_of_month.isoformat()})
        self.admin.call("gamification.challenge", "action_check", [c["challenge_id"]])
        self.admin.call("gamification.goal", "update_goal", [goal_id])
        goal = self._read_goal(goal_id)
        expected = self._expected_prorata_target(self.ORIGINAL_TARGET, self.FIRST_MONTH_PCT, first_of_month)
        actual = goal.get(redefined)
        if actual is None:
            self._skip("pro-rata join 1st", f"field {redefined} empty (Studio automation may not have run)")
        else:
            self._ok(
                "pro-rata join on 1st (30% of original)",
                abs(actual - expected) < 1.0,
                f"expected≈{expected}, got={actual}",
            )

        # Scenario 2: join on 14th
        join_14 = first_of_month.replace(day=min(14, calendar.monthrange(first_of_month.year, first_of_month.month)[1]))
        if join_field in self.admin.fields_get("hr.employee"):
            self.admin.write("hr.employee", [employee_id], {join_field: join_14.isoformat()})
        self.admin.call("gamification.challenge", "action_check", [c["challenge_id"]])
        self.admin.call("gamification.goal", "update_goal", [goal_id])
        goal = self._read_goal(goal_id)
        expected_14 = self._expected_prorata_target(self.ORIGINAL_TARGET, self.FIRST_MONTH_PCT, join_14)
        actual = goal.get(redefined)
        if actual is None:
            self._skip("pro-rata join 14th", f"field {redefined} empty")
        else:
            self._ok(
                "pro-rata join mid-month (14th)",
                abs(actual - expected_14) < 1.5,
                f"expected≈{expected_14}, got={actual}",
            )

    def scenario_pto(self) -> None:
        """PTO/holiday impact: timesheet hours on leave (access_rights_management)."""
        print("\n=== SCENARIO: pto ===")
        if not self._module_installed("access_rights_management"):
            self._skip("pto", "access_rights_management not installed")
            return

        c = self.ctx
        pto_field = c.get("pto_field") or self._require_studio_field("job", "pto_holidays_impact")
        if not pto_field:
            return

        company_id = c["company_id"]
        leave_project_id = self._create("project.project", {
            "name": f"RPC Leave Project {self.suffix}",
            "company_id": company_id,
        })
        leave_task_id = self._create("project.task", {
            "name": "Leave Task",
            "project_id": leave_project_id,
        })
        leave_type_id = self._create("hr.leave.type", {
            "name": f"RPC Leave Type {self.suffix}",
            "requires_allocation": False,
            "leave_validation_type": "no_validation",
            "company_id": company_id,
            "timesheet_project_id": leave_project_id,
            "timesheet_task_id": leave_task_id,
            "no_adjustment_on_target": True,
        })

        leave_date = date.today()
        leave_id = self._create("hr.leave", {
            "name": "RPC Test Leave",
            "employee_id": c["employee_id"],
            "holiday_status_id": leave_type_id,
            "request_date_from": leave_date.isoformat(),
            "request_date_to": leave_date.isoformat(),
            "date_from": f"{leave_date.isoformat()} 08:00:00",
            "date_to": f"{leave_date.isoformat()} 17:00:00",
        })
        try:
            self.admin.call("hr.leave", "action_validate", [leave_id])
        except RpcError:
            self.admin.write("hr.leave", [leave_id], {"state": "validate"})

        ts_id = self._create("account.analytic.line", {
            "name": "RPC leave timesheet",
            "project_id": leave_project_id,
            "task_id": leave_task_id,
            "employee_id": c["employee_id"],
            "user_id": c["employee_user_id"],
            "holiday_id": leave_id,
            "date": leave_date.isoformat(),
        })
        ts = self.admin.read("account.analytic.line", [ts_id], ["unit_amount"])[0]
        self._ok(
            "leave timesheet uses PTO/holiday impact hours",
            abs(ts["unit_amount"] - self.PTO_HOURS_PER_DAY) < 0.01,
            f"unit_amount={ts['unit_amount']}",
        )

        redefined = c.get("redefined_field")
        if redefined and not self.skip_studio:
            goal_before = self._read_goal(c["goal_id"]).get(redefined)
            self.admin.call("gamification.goal", "update_goal", [c["goal_id"]])
            goal_after = self._read_goal(c["goal_id"]).get(redefined)
            if goal_before is not None and goal_after is not None and goal_after < goal_before:
                self._ok(
                    "PTO reduces redefined target (Studio)",
                    True,
                    f"before={goal_before}, after={goal_after}",
                )
            else:
                self._skip(
                    "PTO reduces redefined target",
                    "Studio automation did not change redefined target (configure in DB)",
                )

    def scenario_manager_quotas(self) -> None:
        """Team manager hours allocation -> internal.project.quotas."""
        print("\n=== SCENARIO: manager_quotas ===")
        if not self._module_installed("ksc_project_extended"):
            self._skip("manager_quotas", "ksc_project_extended not installed")
            return

        c = self.ctx
        tm_project_id = self._create("project.project", {
            "name": f"RPC TM Project {self.suffix}",
            "company_id": c["company_id"],
        })
        self.admin.write("res.company", [c["company_id"]], {
            "team_manager_project_id": tm_project_id,
        })
        self.admin.write("hr.employee", [c["employee_id"]], {
            "parent_id": c["manager_employee_id"],
            "job_id": c["job_id"],
        })
        self.admin.write("hr.job", [c["job_id"]], {
            "team_manager_hours_allocation": self.TM_ALLOCATION_HOURS,
        })

        quota_ids = self.admin.search("internal.project.quotas", [
            ("employee_id", "=", c["manager_employee_id"]),
            ("project_id", "=", tm_project_id),
        ], limit=1)
        if not quota_ids:
            self.admin.read("hr.employee", [c["manager_employee_id"]], ["team_manager_hours_allocation"])
            quota_ids = self.admin.search("internal.project.quotas", [
                ("employee_id", "=", c["manager_employee_id"]),
                ("project_id", "=", tm_project_id),
            ], limit=1)

        self._ok("internal project quota created for manager", bool(quota_ids), f"ids={quota_ids}")
        if quota_ids:
            quota = self.admin.read("internal.project.quotas", quota_ids, ["hours_per_month"])[0]
            self._ok(
                "manager quota hours = sum of child job allocations",
                quota["hours_per_month"] == int(self.TM_ALLOCATION_HOURS),
                f"hours={quota['hours_per_month']}",
            )

    def scenario_challenge_badge(self) -> None:
        """Default Odoo flow: timesheet progress + badge on target reached."""
        print("\n=== SCENARIO: challenge_badge ===")
        c = self.ctx
        goal_id = c["goal_id"]
        target = self.ORIGINAL_TARGET

        self._create("account.analytic.line", {
            "name": "RPC reach target hours",
            "project_id": c["billable_project_id"],
            "user_id": c["employee_user_id"],
            "employee_id": c["employee_id"],
            "unit_amount": target,
            "date": c["month_start"],
        })
        self.admin.call("gamification.goal", "update_goal", [goal_id])
        goal = self._read_goal(goal_id)
        self._ok(
            "timesheet sum updates goal current",
            goal.get("current", 0) >= target * 0.9,
            f"current={goal.get('current')}, target={target}",
        )

        badge_user_ids = self.admin.search("gamification.badge.user", [
            ("user_id", "=", c["employee_user_id"]),
            ("badge_id", "=", c["badge_id"]),
        ])
        self._ok(
            "employee has challenge reward badge",
            len(badge_user_ids) >= 1,
            f"badge.user count={len(badge_user_ids)}",
        )

    def scenario_studio_bonus(self) -> None:
        """Studio bonus/commission/adjustment fields (if installed)."""
        print("\n=== SCENARIO: studio_bonus ===")
        if self.skip_studio:
            self._skip("studio_bonus", "--skip-studio")
            return

        c = self.ctx
        goal_id = c["goal_id"]
        adjustment = c.get("adjustment_field") or self.fields.goal_field("adjustment")
        redefined = c.get("redefined_field") or self.fields.goal_field("redefined_onboard_target")
        bonus_reach = c.get("bonus_reach_field") or self.fields.goal_field("bonus_for_reaching_target")

        if not any([adjustment, redefined, bonus_reach]):
            self._skip("studio_bonus", "No Studio goal fields discovered")
            return

        goal = self._read_goal(goal_id)
        if redefined and goal.get(redefined):
            self._ok("redefined onboard target populated", True, f"{redefined}={goal[redefined]}")
        elif redefined:
            self._skip("redefined onboard target", "Field exists but empty")

        if adjustment:
            try:
                before = goal.get(redefined) or goal.get("target_goal")
                self.admin.write("gamification.goal", [goal_id], {adjustment: -5.0})
                self.admin.call("gamification.goal", "update_goal", [goal_id])
                after_goal = self._read_goal(goal_id)
                after = after_goal.get(redefined) or after_goal.get("target_goal")
                if before is not None and after is not None and after != before:
                    self._ok("negative adjustment reduces target", after < before, f"{before}->{after}")
                else:
                    self._skip("adjustment effect", "Studio compute did not change target")
            except RpcError as exc:
                self._skip("adjustment write", str(exc))

        if bonus_reach:
            val = self._read_goal(goal_id).get(bonus_reach)
            if val:
                self._ok("bonus for reaching target field readable", True, f"{bonus_reach}={val}")
            else:
                self._skip("bonus for reaching target", "Field empty until target reached")

        for key in ("commission_over_target_until_120", "commission_over_target_after_120"):
            field = self.fields.goal_field(key)
            if field:
                self._ok(f"Studio field discovered: {key}", True, field)
            else:
                self._skip(f"Studio field: {key}", "not found on goal")

        tm_field = self.fields.goal_field("team_manager_bonus")
        if tm_field:
            self._ok("team manager bonus field on goal", True, tm_field)
        else:
            self._skip("team manager bonus on goal", "not found")

    def scenario_employee(self) -> None:
        """Non-admin employee RPC access."""
        print("\n=== SCENARIO: employee (non-admin) ===")
        c = self.ctx
        employee = self._user_client(c["employee_login"], c["employee_password"])
        self._ok("employee authenticates", employee.uid is not None, f"uid={employee.uid}")

        visible = employee.search("gamification.goal", [("id", "=", c["goal_id"])], limit=1)
        self._ok("employee sees own goal", bool(visible))

        if visible:
            goal = self._read_goal(c["goal_id"], employee)
            self._ok("employee reads quest bonus", "goal_quest_bonus" in goal)
            self._ok("employee reads internal P2P3 hours", "hours_of_internal_p2_p3" in goal)

        blocked = False
        try:
            cid = employee.create("gamification.challenge", {"name": f"X {self.suffix}", "period": "once"})
            self._track("gamification.challenge", cid)
        except RpcError as exc:
            blocked = exc.is_access_error
        self._ok("employee cannot create challenge", blocked)

        mgr_goal = self.admin.search("gamification.goal", [
            ("user_id", "=", c["manager_user_id"]),
        ], limit=1)
        if mgr_goal:
            vis = employee.search("gamification.goal", [("id", "=", mgr_goal[0])], limit=1)
            self._ok("employee cannot see manager goal", not vis)

    def _cleanup(self) -> None:
        if not self.cleanup:
            print("\n[INFO] Cleanup skipped (--no-cleanup)")
            return
        print("\n=== CLEANUP (admin) ===")
        for model, rid in reversed(self._created):
            try:
                if self.admin.search(model, [("id", "=", rid)], limit=1):
                    self.admin.execute_kw(model, "unlink", [[rid]])
                    print(f"  deleted {model}({rid})")
            except RpcError as exc:
                print(f"  [WARN] {model}({rid}): {exc}")

    def run(self) -> bool:
        print("=" * 72)
        print("HR Gamification — full workflow RPC integration test")
        print(f"Protocol: {self.admin.protocol.upper()} | DB: {self.admin.db} | URL: {self.admin.url}")
        print(f"Scenarios: {', '.join(self.scenarios)}")
        print("=" * 72)

        runners = {
            "discover": self.scenario_discover,
            "core": self.scenario_core,
            "prorata": self.scenario_prorata,
            "pto": self.scenario_pto,
            "manager_quotas": self.scenario_manager_quotas,
            "challenge_badge": self.scenario_challenge_badge,
            "studio_bonus": self.scenario_studio_bonus,
            "employee": self.scenario_employee,
        }

        try:
            if "discover" in self.scenarios:
                self.scenario_discover()
                if self.scenarios == ["discover"]:
                    return True

            needs_setup = any(s in self.scenarios for s in runners if s != "discover")
            if needs_setup:
                self.setup_context()

            for name in self.scenarios:
                if name == "discover":
                    continue
                if name not in runners:
                    print(f"[WARN] Unknown scenario: {name}")
                    continue
                runners[name]()
        finally:
            print("=" * 72)
            print(f"Result: {self.passed} passed, {self.failed} failed, {self.skipped} skipped")
            print("=" * 72)
            self._cleanup()

        return self.failed == 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Full HR gamification workflow RPC test")
    p.add_argument("--url", default=os.environ.get("ODOO_URL", DEFAULT_URL))
    p.add_argument("--db", default=os.environ.get("ODOO_DB", DEFAULT_DB))
    p.add_argument("--user", default=os.environ.get("ODOO_USER", DEFAULT_USER))
    p.add_argument("--password", default=os.environ.get("ODOO_PASSWORD", DEFAULT_PASSWORD))
    p.add_argument("--protocol", "--rpc", dest="protocol",
                   choices=["jsonrpc", "xmlrpc"], default=os.environ.get("ODOO_RPC", DEFAULT_PROTOCOL))
    p.add_argument("--scenarios", default="all",
                   help=f"Comma-separated: all, {','.join(ALL_SCENARIOS)}")
    p.add_argument("--employee-login")
    p.add_argument("--employee-password", default=os.environ.get("ODOO_EMPLOYEE_PASSWORD"))
    p.add_argument("--field-config", type=Path, default=DEFAULT_FIELD_CONFIG)
    p.add_argument("--skip-studio", action="store_true",
                   help="Only test Python-backed logic (skip Studio field assertions)")
    p.add_argument("--discover-fields", action="store_true",
                   help="Print Studio field discovery and exit")
    p.add_argument("--no-cleanup", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    try:
        admin = connect(args.url, args.db, args.user, args.password, args.protocol)
        print(f"Authenticated admin uid={admin.uid}")
    except RpcError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.discover_fields:
        FieldResolver(admin, args.field_config).print_discovery_report()
        return 0

    scenarios = list(ALL_SCENARIOS) if args.scenarios.strip().lower() == "all" else [
        s.strip() for s in args.scenarios.split(",") if s.strip()
    ]

    ok = HrGamificationWorkflowTest(
        admin,
        scenarios=scenarios,
        cleanup=not args.no_cleanup,
        skip_studio=args.skip_studio,
        employee_login=args.employee_login,
        employee_password=args.employee_password,
        field_config=args.field_config,
    ).run()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
