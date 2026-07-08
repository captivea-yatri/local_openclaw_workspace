"""Playwright UI smoke for access_rights_management roles."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from cap_qa_platform.rpc.access_matrix import (
    BREAK_CATEGORY_CONFIG_GAP,
    BREAK_CATEGORY_RECORD_SCOPE,
    BREAK_CATEGORY_SECURITY,
    RoleAccessContext,
    compute_role_verdict,
    rpc_check_access,
    rpc_search_outcome,
)
from cap_qa_platform.rpc.client import OdooRPCClient, m2o_id
from cap_qa_platform.rpc.role_manager import RoleManager, TEST_USER_LOGIN, TEST_USER_PASSWORD
from cap_qa_platform.rpc.roles import resolve_roles
from cap_qa_platform.ui.access_rights.app_map import ACCESS_DENIED_MARKERS, UI_SMOKE_PROBES
from cap_qa_platform.ui.config import headless
from cap_qa_platform.ui.pages.login import LoginPage

class AccessRightsRoleUITest:
    """UI companion to test_access_rights_roles_rpc.py.

    Expectations come from live ``ir.model.access`` and ``ir.rule`` rows for the
    role's groups — not from UI page heuristics alone.
    """

    def __init__(
        self,
        admin: OdooRPCClient,
        url: str,
        db: str,
        role_defs: list[tuple[str, str]],
        roles_from: str = "xml",
        role_filter: list[str] | None = None,
        test_login: str = TEST_USER_LOGIN,
        test_password: str = TEST_USER_PASSWORD,
        report_file: str | None = None,
        verbose: bool = False,
    ):
        self.admin = admin
        self.url = url.rstrip("/")
        self.db = db
        self.role_defs = role_defs
        self.roles_from = roles_from
        self.role_filter = role_filter
        self.test_login = test_login
        self.test_password = test_password
        self.report_file = report_file
        self.verbose = verbose
        self.role_manager: RoleManager | None = None
        self.all_breaks: list[dict[str, Any]] = []
        self.role_results: dict[str, dict[str, Any]] = {}

    def _record_break(
        self,
        role_name: str,
        role_id: int,
        model: str,
        message: str,
        category: str,
        acl_grants_read: bool,
        rpc_search: str,
        rpc_check: str,
        ui_outcome: str,
        acl_rules: list[str],
        record_rules: list[str],
    ) -> None:
        entry = {
            "role": role_name,
            "role_id": role_id,
            "model": model,
            "operation": "read",
            "layer": "ui",
            "category": category,
            "message": message,
            "acl_grants_read": acl_grants_read,
            "rpc_search": rpc_search,
            "rpc_check": rpc_check,
            "ui_outcome": ui_outcome,
            "acl_rules": acl_rules,
            "record_rules": record_rules,
        }
        self.all_breaks.append(entry)
        print(f"    [BREAK] {role_name} | {model} | {category} | {message}")

    def _classify_page(self, page) -> str:
        url = page.url.lower()
        if "/web/login" in url:
            return "login"
        if url.rstrip("/").endswith("/my") or "/my/" in url:
            return "portal"
        try:
            body = page.locator("body").inner_text(timeout=5000).lower()
        except Exception:
            body = ""
        if any(m in body for m in ACCESS_DENIED_MARKERS):
            return "denied"
        return "ok"

    def _probe_path(self, page, path: str) -> str:
        page.goto(f"{self.url}{path}", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        return self._classify_page(page)

    def _app_on_home(self, page, app_name: str) -> bool:
        page.goto(f"{self.url}/odoo", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        return page.get_by_text(app_name, exact=True).count() > 0

    def _test_role_ui(
        self,
        page,
        tester: OdooRPCClient,
        role_name: str,
        role_id: int,
        access_ctx: RoleAccessContext,
    ) -> dict[str, Any]:
        print(f"\n--- UI smoke: {role_name} (id={role_id}) ---")
        print(
            f"  ACL rows: {len(access_ctx.access_rules)} | "
            f"Record rules: {len(access_ctx.record_rules)}"
        )
        passed = failed = skipped = 0
        probes: list[dict[str, Any]] = []

        for probe in UI_SMOKE_PROBES:
            model = probe["model"]
            app = probe["app"]
            path = probe["path"]
            acl_read = access_ctx.acl_grants_read(model)
            acl_rules = access_ctx.acl_rule_names(model)
            record_rules = access_ctx.record_rule_names(model)
            rpc_search = rpc_search_outcome(tester, model)
            rpc_check = rpc_check_access(tester, model, "read")

            if rpc_search == "skip" and rpc_check == "skip":
                skipped += 1
                probes.append(
                    {
                        "model": model,
                        "acl_grants_read": acl_read,
                        "rpc_search": rpc_search,
                        "rpc_check": rpc_check,
                        "ui_outcome": "skip",
                        "verdict": "SKIP",
                        "acl_rules": acl_rules,
                        "record_rules": record_rules,
                    }
                )
                continue

            ui_path = self._probe_path(page, path)
            app_visible = self._app_on_home(page, app) if app else False

            verdict = "PASS"
            category = ""

            if not acl_read:
                # No ir.model.access / ir.rule read grant for this role's groups.
                if rpc_search == "ok" or rpc_check == "allowed":
                    verdict = "FAIL"
                    failed += 1
                    category = BREAK_CATEGORY_SECURITY
                    self._record_break(
                        role_name,
                        role_id,
                        model,
                        "ACL/record rules deny read but RPC allows access",
                        category,
                        acl_read,
                        rpc_search,
                        rpc_check,
                        ui_path,
                        acl_rules,
                        record_rules,
                    )
                # UI app shell without RPC data access is not a violation.
            else:
                # ACL / rules grant read — UI and RPC must not block.
                if ui_path in ("denied", "login", "portal"):
                    verdict = "FAIL"
                    failed += 1
                    category = BREAK_CATEGORY_CONFIG_GAP
                    self._record_break(
                        role_name,
                        role_id,
                        model,
                        f"ACL/rules grant read but UI path {path} -> {ui_path}",
                        category,
                        acl_read,
                        rpc_search,
                        rpc_check,
                        ui_path,
                        acl_rules,
                        record_rules,
                    )
                elif rpc_search == "denied" or rpc_check == "denied":
                    verdict = "FAIL"
                    failed += 1
                    category = (
                        BREAK_CATEGORY_RECORD_SCOPE
                        if record_rules
                        else BREAK_CATEGORY_CONFIG_GAP
                    )
                    self._record_break(
                        role_name,
                        role_id,
                        model,
                        "ACL/rules grant read but RPC search/check denied",
                        category,
                        acl_read,
                        rpc_search,
                        rpc_check,
                        ui_path,
                        acl_rules,
                        record_rules,
                    )
                else:
                    passed += 1

            probes.append(
                {
                    "model": model,
                    "app": app,
                    "path": path,
                    "acl_grants_read": acl_read,
                    "rpc_search": rpc_search,
                    "rpc_check": rpc_check,
                    "ui_path": ui_path,
                    "app_visible": app_visible,
                    "verdict": verdict,
                    "category": category or None,
                    "acl_rules": acl_rules,
                    "record_rules": record_rules,
                }
            )
            if self.verbose:
                print(
                    f"  {model:<25} acl={str(acl_read):<5} rpc={rpc_search:<7} "
                    f"check={rpc_check:<7} ui={ui_path:<7} {verdict}"
                )

        breaks = [b for b in self.all_breaks if b["role"] == role_name]
        access_verdict = compute_role_verdict(breaks)

        return {
            "role": role_name,
            "role_id": role_id,
            "verdict": access_verdict["verdict"],
            "summary": access_verdict["summary"],
            "security_violations": access_verdict["security_violations"],
            "config_gaps": access_verdict["config_gaps"],
            "acl_rows": len(access_ctx.access_rules),
            "record_rules_count": len(access_ctx.record_rules),
            "ui_pass": passed,
            "ui_fail": failed,
            "ui_skip": skipped,
            "break_count": len(breaks),
            "probes": probes,
        }

    def run(self) -> bool:
        from playwright.sync_api import sync_playwright

        roles = resolve_roles(self.admin, self.role_defs, self.roles_from)
        if self.role_filter:
            wanted = {n.lower() for n in self.role_filter}
            roles = [r for r in roles if r["name"].lower() in wanted]
        if not roles:
            print("ERROR: No roles found.")
            return False

        company_id = m2o_id(
            self.admin.read("res.users", [self.admin.uid], ["company_id"])[0]["company_id"]
        )
        if not company_id:
            print("ERROR: Admin user has no company_id.")
            return False

        self.role_manager = RoleManager(
            self.admin, self.test_login, self.test_password
        )
        self.role_manager.ensure_test_user(company_id)
        self.role_manager.backup_role_lines()

        print("=" * 80)
        print("Access Rights Management — Role UI Smoke (Playwright)")
        print("Expectations: ir.model.access + ir.rule (live DB)")
        print(f"URL: {self.url} | DB: {self.db} | Probes: {len(UI_SMOKE_PROBES)}")
        print("=" * 80)

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=headless())
                for role in roles:
                    try:
                        access_ctx = RoleAccessContext(
                            self.admin, role["id"], role["name"]
                        )
                    except Exception as exc:
                        print(f"  [ERROR] Cannot load ACL/rules for {role['name']}: {exc}")
                        self.role_results[role["name"]] = {
                            "role": role["name"],
                            "role_id": role["id"],
                            "verdict": "ERROR",
                            "error": f"acl load: {exc}",
                        }
                        continue
                    try:
                        self.role_manager.assign_single_role(role["id"])
                    except Exception as exc:
                        print(f"  [ERROR] Cannot assign role {role['name']}: {exc}")
                        self.role_results[role["name"]] = {
                            "role": role["name"],
                            "role_id": role["id"],
                            "verdict": "ERROR",
                            "error": str(exc),
                        }
                        continue
                    tester = OdooRPCClient(
                        self.url, self.db, self.test_login, self.test_password
                    )
                    try:
                        tester.authenticate()
                    except Exception as exc:
                        print(f"  [ERROR] RPC login failed for {role['name']}: {exc}")
                        self.role_results[role["name"]] = {
                            "role": role["name"],
                            "role_id": role["id"],
                            "verdict": "ERROR",
                            "error": f"rpc login: {exc}",
                        }
                        continue
                    context = browser.new_context()
                    page = context.new_page()
                    login = LoginPage(page, self.url)
                    try:
                        login.login(self.db, self.test_login, self.test_password)
                    except Exception as exc:
                        print(f"  [ERROR] UI login failed for {role['name']}: {exc}")
                        self.role_results[role["name"]] = {
                            "role": role["name"],
                            "role_id": role["id"],
                            "verdict": "ERROR",
                            "error": f"ui login: {exc}",
                        }
                        context.close()
                        continue
                    if not login.is_logged_in():
                        print(f"  [FAIL] UI login failed for {self.test_login}: {page.url}")
                        self.role_results[role["name"]] = {
                            "role": role["name"],
                            "role_id": role["id"],
                            "verdict": "ERROR",
                            "error": f"login failed: {page.url}",
                        }
                        context.close()
                        continue
                    self.role_results[role["name"]] = self._test_role_ui(
                        page, tester, role["name"], role["id"], access_ctx
                    )
                    context.close()
        finally:
            if self.role_manager:
                try:
                    self.role_manager.restore_role_lines()
                except Exception:
                    pass
            self._print_summary()
            if self.report_file:
                self._write_report(len(roles))

        has_violations = any(
            r.get("verdict") == "VIOLATES" for r in self.role_results.values()
        )
        has_errors = any(
            r.get("verdict") == "ERROR" for r in self.role_results.values()
        )
        return not (has_violations or has_errors)

    def _print_summary(self) -> None:
        print("\n" + "=" * 80)
        print("UI ROLE SUMMARY (ACL + record rules)")
        print("=" * 80)
        print(
            f"{'Role':<28} {'Verdict':<10} {'Sec':<4} {'Gap':<4} "
            f"{'Pass':<6} {'Fail':<6} {'Skip':<6}"
        )
        print("-" * 80)
        for name, res in self.role_results.items():
            print(
                f"{name:<28} {res.get('verdict', '?'):<10} "
                f"{res.get('security_violations', 0):<4} "
                f"{res.get('config_gaps', 0):<4} "
                f"{res.get('ui_pass', 0):<6} {res.get('ui_fail', 0):<6} "
                f"{res.get('ui_skip', 0):<6}"
            )
        print("=" * 80)
        print(f"Total breaks: {len(self.all_breaks)}")

    def _write_report(self, role_count: int) -> None:
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "url": self.url,
            "db": self.db,
            "expectation_source": "ir.model.access + ir.rule",
            "role_count": role_count,
            "probe_count": len(UI_SMOKE_PROBES),
            "breaks": self.all_breaks,
            "roles": self.role_results,
        }
        path = self.report_file
        assert path
        if path.endswith(".csv"):
            import csv

            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(
                    fh,
                    fieldnames=[
                        "role",
                        "role_id",
                        "model",
                        "category",
                        "message",
                        "acl_grants_read",
                        "rpc_search",
                        "rpc_check",
                        "ui_outcome",
                        "acl_rules",
                        "record_rules",
                    ],
                )
                writer.writeheader()
                for row in self.all_breaks:
                    out = dict(row)
                    out["acl_rules"] = "; ".join(row.get("acl_rules") or [])
                    out["record_rules"] = "; ".join(row.get("record_rules") or [])
                    writer.writerow(out)
        else:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
        print(f"Report written: {path}")
