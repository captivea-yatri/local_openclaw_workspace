#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Production tracer for mail.activity Missing Record errors
(quality.issue.log + approval.request workflow).

Read-only diagnostics via XML-RPC / JSON-RPC. Does NOT modify module code or
production data (no create/write/unlink).

Use this when a user reports:
  Missing Record — Record does not exist or has been deleted.
  (Record: mail.activity(1743636,), User: 42)

---------------------------------------------------------------------------
QUICK START
---------------------------------------------------------------------------

# Full audit for a affected user (by user id from the error message)
python3 scripts/trace_mail_activity_errors.py \\
  --url https://your-odoo.com --db PROD_DB --user admin --password '***' \\
  --user-id 42

# Investigate a specific deleted activity id from the error popup
python3 scripts/trace_mail_activity_errors.py \\
  --url https://your-odoo.com --db PROD_DB --user admin --password '***' \\
  --activity-id 1743636 --user-id 42

# Full trace: reproduce RPC error + map to source code files + reverse lookup
python3 scripts/trace_mail_activity_errors.py \\
  --url http://localhost:8069 --db odoo --user admin --password admin \\
  --activity-id 1743636 --user-id 42 --output /tmp/trace_report.json

# Save JSON report
python3 scripts/trace_mail_activity_errors.py ... --output /tmp/qil_trace_report.json

# Also search ir.logging (only works if DB logging is enabled in odoo.conf)
python3 scripts/trace_mail_activity_errors.py ... --search-logs --log-days 14

---------------------------------------------------------------------------
WHY UI / TEST SCRIPTS OFTEN FAIL TO REPRODUCE
---------------------------------------------------------------------------
This error is usually caused by a STALE browser reference to an activity that
was already deleted server-side (approve, refuse, ask_for_review again, or
approval._cancel_activities). The systray/notification keeps the old id until
the page is refreshed. Automated tests create fresh sessions without that cache.

---------------------------------------------------------------------------
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

# Reuse RPC client from the test script (same directory)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from test_quality_issue_approval_rpc import RpcError, connect  # noqa: E402


LEGACY_ACTIVITY_SUMMARY = "Review Quality Issue"
QIL_MODEL = "quality.issue.log"
APPROVAL_MODEL = "approval.request"

# Maps workflow paths to the custom/Odoo code that creates, deletes, or skips activities.
CODE_PATHS = {
    "approval_request": {
        "label": "Approval Request activity (Approvals app)",
        "create": [
            {
                "module": "access_rights_management",
                "file": "models/approval_request.py",
                "method": "action_confirm()",
                "detail": "Line ~59: approvers._create_activity() after manager checks",
            },
            {
                "module": "approvals (Odoo Enterprise)",
                "file": "models/approval_approver.py",
                "method": "_create_activity()",
                "detail": "Core: creates mail.activity on approval.request for each pending approver",
            },
        ],
        "delete": [
            {
                "module": "approvals (Odoo Enterprise)",
                "method": "action_approve() / action_refuse()",
                "detail": "Core calls _cancel_activities() / action_feedback — NOT overridden in your modules",
            },
        ],
        "gaps": [
            {
                "module": "cap_quality_issue_log",
                "file": "models/quality_issue_log.py",
                "method": "accept_review() / refuse_review()",
                "detail": "Do not unlink mail.activity or sync with approval.request",
            },
            {
                "module": "access_rights_management",
                "file": "models/approval_request.py",
                "detail": "No override on action_approve/action_refuse to update quality.issue.log state",
            },
        ],
        "ui_error_trigger": "Bell / Activities / activity popup → RPC mail.activity.read(id) or action_feedback(id)",
        "ui_still_works": "Approve/Refuse on approval.request form → RPC approval.request.action_approve(id)",
    },
    "qil_legacy_todo": {
        "label": "Legacy Ask For Review To-Do (quality.issue.log)",
        "create": [
            {
                "module": "cap_quality_issue_log",
                "file": "models/quality_issue_log.py",
                "method": "ask_for_review()",
                "detail": "Creates To-Do with summary 'Review Quality Issue' on quality.issue.log",
            },
        ],
        "delete": [
            {
                "module": "(none in custom code)",
                "detail": "accept_review() / refuse_review() change state only — activity is NOT removed",
            },
        ],
        "gaps": [
            {
                "module": "cap_quality_issue_log",
                "file": "models/quality_issue_log.py",
                "method": "accept_review() / refuse_review()",
                "detail": "Should unlink open activities (see cap_actions/models/action_validation.py for pattern)",
            },
        ],
        "ui_error_trigger": "Bell / Activities on legacy To-Do after manual delete or duplicate ask_for_review",
        "ui_still_works": "Accept/Refuse Review buttons on quality.issue.log form (no activity RPC)",
    },
}


def _section(title):
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def _info(k, v):
    print(f"  {k}: {v}")


def _warn(msg):
    print(f"  [!] {msg}")


def _ok(msg):
    print(f"  [ok] {msg}")


class MailActivityTracer:
    def __init__(self, client):
        self.c = client
        self.report = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "database": client.db,
            "url": client.url,
            "findings": [],
            "risky_records": [],
        }

    def _add_finding(self, severity, code, message, data=None):
        entry = {"severity": severity, "code": code, "message": message}
        if data:
            entry["data"] = data
        self.report["findings"].append(entry)
        prefix = {"high": "[HIGH]", "medium": "[MED]", "low": "[LOW]", "info": "[INFO]"}[severity]
        print(f"  {prefix} {message}")
        if data:
            for k, v in data.items():
                print(f"         {k} = {v}")

    def _model_available(self, model):
        try:
            self.c.fields_get(model, attributes=["type"])
            return True
        except RpcError:
            return False

    def _approval_activity_type_id(self):
        rows = self.c.search_read(
            "ir.model.data",
            [("module", "=", "approvals"), ("name", "=", "mail_activity_data_approval")],
            fields=["res_id"],
            limit=1,
        )
        return rows[0]["res_id"] if rows else None

    def _qil_link_field_on_approval(self):
        if not self._model_available(APPROVAL_MODEL):
            return None
        fields = self.c.fields_get(APPROVAL_MODEL, attributes=["type"])
        if "quality_issue_log_id" in fields:
            return "quality_issue_log_id"
        if "x_studio_quality_issue_log" in fields:
            return "x_studio_quality_issue_log"
        return None

    def _resolve_user(self, user_id=None, login=None):
        if user_id:
            users = self.c.read("res.users", [user_id], fields=["id", "name", "login", "partner_id"])
            if users:
                return users[0]
            return None
        if login:
            rows = self.c.search_read("res.users", [("login", "=", login)], fields=["id", "name", "login", "partner_id"], limit=1)
            return rows[0] if rows else None
        return None

    def _record_exists(self, model, res_id):
        if not res_id or not self._model_available(model):
            return False
        try:
            rows = self.c.read(model, [res_id], fields=["id"])
            return bool(rows)
        except RpcError:
            return False

    def _classify_activity_path(self, res_model, summary=None, activity_type_id=None):
        """Return CODE_PATHS key for an activity or inferred document."""
        approval_type_id = self._approval_activity_type_id()
        if res_model == APPROVAL_MODEL:
            return "approval_request"
        if res_model == QIL_MODEL and summary == LEGACY_ACTIVITY_SUMMARY:
            return "qil_legacy_todo"
        if res_model == QIL_MODEL:
            return "qil_legacy_todo"
        return None

    def print_code_path(self, path_key, context=None):
        """Print human-readable code trace for a workflow path."""
        spec = CODE_PATHS.get(path_key)
        if not spec:
            _warn(f"No code path map for {path_key!r}")
            return

        _section(f"CODE PATH — {spec['label']}")
        if context:
            for k, v in context.items():
                _info(k, v)

        print("\n  CREATE (where activity comes from):")
        for row in spec["create"]:
            loc = f"{row['module']}/{row['file']}" if row.get("file") else row["module"]
            print(f"    • {loc} → {row['method']}")
            if row.get("detail"):
                print(f"      {row['detail']}")

        print("\n  DELETE (what removes the activity):")
        for row in spec["delete"]:
            method = row.get("method", "")
            print(f"    • {row['module']}" + (f" → {method}" if method else ""))
            if row.get("detail"):
                print(f"      {row['detail']}")

        print("\n  GAPS in your custom code (likely fix locations):")
        for row in spec["gaps"]:
            loc = f"{row['module']}/{row['file']}" if row.get("file") else row["module"]
            method = f" → {row['method']}" if row.get("method") else ""
            print(f"    • {loc}{method}")
            if row.get("detail"):
                print(f"      {row['detail']}")

        print(f"\n  UI → Missing Record: {spec['ui_error_trigger']}")
        print(f"  UI → still works:     {spec['ui_still_works']}")

        entry = {"path_key": path_key, "label": spec["label"], "context": context or {}}
        self.report.setdefault("code_traces", []).append(entry)

    def reproduce_missing_record(self, activity_id):
        """
        Replay the RPC calls the Odoo web client makes when opening/completing
        a deleted activity. Confirms the exact server error from the popup.
        """
        _section(f"RPC REPRODUCE — mail.activity({activity_id}) Missing Record")

        attempts = [
            ("mail.activity / read", lambda: self.c.read(
                "mail.activity", [activity_id],
                fields=["id", "summary", "res_model", "res_id", "user_id"],
            )),
            ("mail.activity / action_feedback", lambda: self.c.call(
                "mail.activity", "action_feedback", [activity_id],
            )),
        ]

        results = {}
        any_missing = False
        for label, fn in attempts:
            try:
                fn()
                results[label] = {"missing_record": False, "reproduced": False, "error": None}
                _info(label, "succeeded (activity exists — error not reproduced now)")
            except RpcError as exc:
                is_missing = exc.is_missing_record
                results[label] = {
                    "missing_record": is_missing,
                    "reproduced": is_missing,
                    "error": str(exc),
                }
                if is_missing:
                    any_missing = True
                    _ok(f"{label} → Missing Record reproduced: {exc}")
                else:
                    _warn(f"{label} → other RPC error: {exc}")

        self.report["reproduce"] = results
        if any_missing:
            self._add_finding(
                "high", "error_reproduced",
                f"Missing Record reproduced via RPC on mail.activity({activity_id})",
                results,
            )
        return results

    def trace_document_chain(self, res_model, res_id, user_id=None):
        """Follow res_model/res_id from activity to related QIL / approval records."""
        _section(f"DOCUMENT CHAIN — {res_model}({res_id})")

        chain = {"res_model": res_model, "res_id": res_id, "related": {}}

        if not self._record_exists(res_model, res_id):
            _warn(f"Document {res_model}({res_id}) no longer exists")
            chain["document_exists"] = False
            self.report.setdefault("document_chains", []).append(chain)
            return chain

        chain["document_exists"] = True
        if res_model == QIL_MODEL:
            log = self.c.read(QIL_MODEL, [res_id], fields=[
                "id", "display_name", "state", "employee_id", "write_date",
            ])[0]
            chain["quality_log"] = log
            _info("Quality log", f"{log['id']} state={log['state']} {log.get('display_name')}")

            link_field = self._qil_link_field_on_approval()
            if link_field and self._model_available(APPROVAL_MODEL):
                approvals = self.c.search_read(
                    APPROVAL_MODEL, [(link_field, "=", res_id)],
                    fields=["id", "name", "request_status", "write_date"],
                    limit=5,
                )
                chain["related"]["approvals"] = approvals
                for appr in approvals:
                    act_count = len(self.c.search("mail.activity", [
                        ("res_model", "=", APPROVAL_MODEL),
                        ("res_id", "=", appr["id"]),
                    ]))
                    _info(f"  Linked approval {appr['id']}", f"status={appr['request_status']}, activities={act_count}")

        elif res_model == APPROVAL_MODEL:
            fields = ["id", "name", "request_status", "request_owner_id", "write_date"]
            link_field = self._qil_link_field_on_approval()
            if link_field:
                fields.append(link_field)
            approval = self.c.read(APPROVAL_MODEL, [res_id], fields=fields)[0]
            chain["approval"] = approval
            _info("Approval", f"{approval['id']} status={approval['request_status']} {approval.get('name')}")

            if link_field and approval.get(link_field):
                qil_id = approval[link_field][0] if isinstance(approval[link_field], (list, tuple)) else approval[link_field]
                if self._record_exists(QIL_MODEL, qil_id):
                    qil = self.c.read(QIL_MODEL, [qil_id], fields=["id", "state", "display_name"])[0]
                    chain["related"]["quality_log"] = qil
                    _info("  Linked QIL", f"{qil['id']} state={qil['state']}")

            if user_id:
                approver_lines = self.c.search_read(
                    "approval.approver",
                    [("request_id", "=", res_id), ("user_id", "=", user_id)],
                    fields=["id", "status"],
                )
                chain["related"]["approver_lines"] = approver_lines
                for line in approver_lines:
                    _info("  Approver line for user", f"status={line['status']}")

        self.report.setdefault("document_chains", []).append(chain)
        return chain

    def trace_back_deleted_activity(self, activity_id, user_id=None):
        """
        When the activity row is gone, infer the most likely workflow origin
        from current DB state (finished approvals, reviewing QILs, etc.).
        """
        _section(f"REVERSE TRACE — infer origin of deleted mail.activity({activity_id})")

        candidates = []
        if user_id:
            candidates.extend(self._infer_origins_for_user(user_id))

        # Search chatter for the numeric activity id (rare but definitive)
        msg_hits = self._search_messages_for_activity_id(activity_id)
        if msg_hits:
            for hit in msg_hits:
                candidates.append({
                    "confidence": "definitive",
                    "path_key": self._classify_activity_path(hit.get("model"), hit.get("summary")),
                    "reason": f"mail.message {hit['id']} references activity id in body/subject",
                    "res_model": hit.get("model"),
                    "res_id": hit.get("res_id"),
                    "message_id": hit["id"],
                })

        if not candidates:
            _warn("Could not infer document from DB — use SQL hints below or server logs at error time")
            self.report["inferred_origins"] = []
            return []

        # De-duplicate and sort by confidence
        seen = set()
        unique = []
        rank = {"definitive": 0, "high": 1, "medium": 2, "low": 3}
        for c in sorted(candidates, key=lambda x: rank.get(x["confidence"], 9)):
            key = (c.get("res_model"), c.get("res_id"), c.get("path_key"))
            if key in seen:
                continue
            seen.add(key)
            unique.append(c)

        self.report["inferred_origins"] = unique
        _info("Likely origins found", len(unique))

        for i, c in enumerate(unique[:5], 1):
            print(f"\n  --- Candidate {i} [{c['confidence']}] ---")
            _info("Reason", c["reason"])
            if c.get("res_model"):
                _info("Document", f"{c['res_model']}({c.get('res_id')})")
            path_key = c.get("path_key") or self._classify_activity_path(c.get("res_model"))
            if path_key:
                ctx = {k: v for k, v in c.items() if k not in ("path_key", "confidence", "reason")}
                self.print_code_path(path_key, context=ctx)
                if c.get("res_model") and c.get("res_id"):
                    self.trace_document_chain(c["res_model"], c["res_id"], user_id=user_id)

        return unique

    def _infer_origins_for_user(self, user_id):
        """Build candidate list from approvals + QIL state for the affected user."""
        candidates = []
        approval_type_id = self._approval_activity_type_id()
        link_field = self._qil_link_field_on_approval()

        if self._model_available(APPROVAL_MODEL):
            # Finished approvals: activity deleted after approve/refuse (most common)
            finished_lines = self.c.search_read(
                "approval.approver",
                [("user_id", "=", user_id), ("status", "in", ["approved", "refused"])],
                fields=["request_id", "status", "write_date"],
                order="write_date desc",
                limit=25,
            )
            for line in finished_lines:
                req_id = line["request_id"][0]
                act_domain = [
                    ("res_model", "=", APPROVAL_MODEL),
                    ("res_id", "=", req_id),
                    ("user_id", "=", user_id),
                ]
                if approval_type_id:
                    act_domain.append(("activity_type_id", "=", approval_type_id))
                if self.c.search("mail.activity", act_domain, limit=1):
                    continue

                approval = self.c.read(
                    APPROVAL_MODEL, [req_id],
                    fields=["id", "name", "request_status", "write_date"],
                )[0]
                ctx = {
                    "approval_id": req_id,
                    "approver_status": line["status"],
                    "approval_status": approval["request_status"],
                    "approver_write_date": line.get("write_date"),
                }
                if link_field:
                    appr_full = self.c.read(APPROVAL_MODEL, [req_id], fields=[link_field])[0]
                    qil_ref = appr_full.get(link_field)
                    if qil_ref:
                        qil_id = qil_ref[0] if isinstance(qil_ref, (list, tuple)) else qil_ref
                        ctx["linked_qil_id"] = qil_id
                        if self._record_exists(QIL_MODEL, qil_id):
                            qil = self.c.read(QIL_MODEL, [qil_id], fields=["state"])[0]
                            ctx["linked_qil_state"] = qil["state"]
                            if qil["state"] == "reviewing":
                                ctx["state_mismatch"] = (
                                    f"QIL still reviewing but approval is {approval['request_status']}"
                                )

                candidates.append({
                    "confidence": "high",
                    "path_key": "approval_request",
                    "reason": (
                        f"User finished as approver on approval {req_id} ({line['status']}) "
                        f"and no open approval activity remains — typical after approve/refuse"
                    ),
                    "res_model": APPROVAL_MODEL,
                    "res_id": req_id,
                    **ctx,
                })

            # Pending approver but activity missing (deleted orphan scenario)
            pending_lines = self.c.search_read(
                "approval.approver",
                [("user_id", "=", user_id), ("status", "=", "pending")],
                fields=["request_id", "write_date"],
                order="write_date desc",
                limit=15,
            )
            for line in pending_lines:
                req_id = line["request_id"][0]
                act_domain = [
                    ("res_model", "=", APPROVAL_MODEL),
                    ("res_id", "=", req_id),
                    ("user_id", "=", user_id),
                ]
                if approval_type_id:
                    act_domain.append(("activity_type_id", "=", approval_type_id))
                if self.c.search("mail.activity", act_domain, limit=1):
                    continue
                candidates.append({
                    "confidence": "medium",
                    "path_key": "approval_request",
                    "reason": (
                        f"User is pending approver on approval {req_id} "
                        f"but mail.activity was deleted — broken pending state"
                    ),
                    "res_model": APPROVAL_MODEL,
                    "res_id": req_id,
                })

        # Legacy QIL To-Dos assigned to user
        if self._model_available(QIL_MODEL):
            legacy_acts = self.c.search_read(
                "mail.activity",
                [
                    ("user_id", "=", user_id),
                    ("res_model", "=", QIL_MODEL),
                    ("summary", "=", LEGACY_ACTIVITY_SUMMARY),
                ],
                fields=["id", "res_id", "create_date"],
                order="create_date desc",
                limit=10,
            )
            for act in legacy_acts:
                candidates.append({
                    "confidence": "low",
                    "path_key": "qil_legacy_todo",
                    "reason": f"Open legacy To-Do activity {act['id']} still exists on QIL {act['res_id']}",
                    "res_model": QIL_MODEL,
                    "res_id": act["res_id"],
                    "open_activity_id": act["id"],
                })

            # Reviewing QILs without activity (deleted legacy todo)
            managed = self.c.search("hr.employee", [("parent_id.user_id", "=", user_id)], limit=200)
            if managed:
                reviewing = self.c.search_read(
                    QIL_MODEL,
                    [("employee_id", "in", managed), ("state", "=", "reviewing")],
                    fields=["id", "display_name", "write_date"],
                    order="write_date desc",
                    limit=20,
                )
                for log in reviewing:
                    qil_acts = self.c.search("mail.activity", [
                        ("res_model", "=", QIL_MODEL),
                        ("res_id", "=", log["id"]),
                        ("user_id", "=", user_id),
                    ])
                    if qil_acts:
                        continue
                    candidates.append({
                        "confidence": "medium",
                        "path_key": "qil_legacy_todo",
                        "reason": (
                            f"QIL {log['id']} is reviewing but user has no open To-Do activity "
                            f"(activity may have been deleted)"
                        ),
                        "res_model": QIL_MODEL,
                        "res_id": log["id"],
                    })

        return candidates

    def _search_messages_for_activity_id(self, activity_id):
        """Best-effort search for chatter messages mentioning the activity id."""
        if not self._model_available("mail.message"):
            return []
        needle = str(activity_id)
        try:
            return self.c.search_read(
                "mail.message",
                [
                    ("model", "in", [QIL_MODEL, APPROVAL_MODEL, "mail.activity"]),
                    "|",
                    ("body", "ilike", needle),
                    ("subject", "ilike", needle),
                ],
                fields=["id", "model", "res_id", "date", "subject"],
                order="date desc",
                limit=10,
            )
        except RpcError:
            return []

    # ------------------------------------------------------------------
    # 1. Investigate specific activity id from error message
    # ------------------------------------------------------------------

    def investigate_activity_id(self, activity_id, user_id=None, reproduce=True, code_path=True):
        _section(f"ACTIVITY INVESTIGATION — mail.activity({activity_id})")

        exists_now = self.c.exists("mail.activity", activity_id)
        _info("Activity exists in DB now", exists_now)

        self.report["activity_id"] = activity_id
        self.report["activity_exists"] = exists_now

        if exists_now:
            act = self.c.read("mail.activity", [activity_id], fields=[
                "id", "summary", "res_model", "res_id", "user_id",
                "activity_type_id", "date_deadline", "create_date", "write_date",
            ])[0]
            _info("Summary", act.get("summary"))
            _info("Assigned to", act.get("user_id"))
            _info("Document", f"{act.get('res_model')}({act.get('res_id')})")
            _info("Created", act.get("create_date"))
            _info("Last updated", act.get("write_date"))

            self.report["activity"] = act

            doc_ok = self._record_exists(act["res_model"], act["res_id"])
            _info("Underlying document exists", doc_ok)
            if not doc_ok:
                self._add_finding(
                    "high", "orphan_activity_document",
                    f"Activity {activity_id} points to deleted {act['res_model']}({act['res_id']})",
                    {"activity_id": activity_id, "res_model": act["res_model"], "res_id": act["res_id"]},
                )
            else:
                self._add_finding("info", "activity_alive", f"Activity {activity_id} is valid right now", act)

            if code_path:
                path_key = self._classify_activity_path(
                    act["res_model"], summary=act.get("summary"),
                )
                if path_key:
                    self.print_code_path(path_key, context={
                        "activity_id": activity_id,
                        "res_model": act["res_model"],
                        "res_id": act["res_id"],
                        "summary": act.get("summary"),
                    })

            uid = user_id
            if not uid and act.get("user_id"):
                uid = act["user_id"][0] if isinstance(act["user_id"], (list, tuple)) else act["user_id"]
            self.trace_document_chain(act["res_model"], act["res_id"], user_id=uid)
            return act

        # Activity was deleted — this matches the production error
        self._add_finding(
            "high", "activity_deleted",
            f"mail.activity({activity_id}) no longer exists — this IS the Missing Record error",
            {"activity_id": activity_id, "user_id": user_id},
        )

        if reproduce:
            self.reproduce_missing_record(activity_id)

        self.trace_back_deleted_activity(activity_id, user_id=user_id)

        if user_id:
            self._trace_deleted_activity_for_user(activity_id, user_id)

        self._print_deleted_activity_sql_hints(activity_id, user_id)
        return None

    def _trace_deleted_activity_for_user(self, activity_id, user_id):
        _section("CONTEXT — user open activities (quality / approval)")

        user = self._resolve_user(user_id=user_id)
        if not user:
            _warn(f"User id {user_id} not found")
            return

        _info("User", f"{user['name']} <{user['login']}> (id={user['id']})")

        approval_type_id = self._approval_activity_type_id()
        domains = [
            ("All open activities for user", [
                ("user_id", "=", user_id),
                ("res_model", "in", [QIL_MODEL, APPROVAL_MODEL]),
            ]),
        ]
        if approval_type_id:
            domains.append(("Approval-type activities", [
                ("user_id", "=", user_id),
                ("res_model", "=", APPROVAL_MODEL),
                ("activity_type_id", "=", approval_type_id),
            ]))
        domains.append(("Legacy QIL review To-Dos", [
            ("user_id", "=", user_id),
            ("res_model", "=", QIL_MODEL),
            ("summary", "=", LEGACY_ACTIVITY_SUMMARY),
        ]))

        for label, domain in domains:
            acts = self.c.search_read(
                "mail.activity", domain,
                fields=["id", "summary", "res_model", "res_id", "create_date"],
                order="create_date desc",
                limit=20,
            )
            print(f"\n  --- {label} ({len(acts)} found) ---")
            for a in acts:
                doc_ok = self._record_exists(a["res_model"], a["res_id"])
                flag = "" if doc_ok else " [BROKEN DOC]"
                print(f"    activity {a['id']}: {a['res_model']}({a['res_id']}) "
                      f"«{a.get('summary')}» created {a.get('create_date')}{flag}")

        # Notifications may still reference deleted activities in mail.message
        partner_id = user["partner_id"][0] if user.get("partner_id") else None
        if partner_id:
            self._search_related_messages(partner_id, activity_id)

    def _search_related_messages(self, partner_id, activity_id):
        _section("RELATED mail.message search (notifications)")
        # Best-effort: messages for this partner mentioning quality/approval recently
        since = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        messages = self.c.search_read(
            "mail.message",
            [
                ("partner_ids", "in", [partner_id]),
                ("create_date", ">=", since),
                "|", "|",
                ("body", "ilike", "quality"),
                ("body", "ilike", "approval"),
                ("body", "ilike", "Review Quality Issue"),
            ],
            fields=["id", "subject", "model", "res_id", "date", "body"],
            order="date desc",
            limit=15,
        )
        if not messages:
            _info("Recent messages", "none matched (notifications may not contain activity id)")
            return
        _info("Recent related messages", len(messages))
        for m in messages:
            body_preview = (m.get("body") or "")[:120].replace("\n", " ")
            print(f"    msg {m['id']} [{m.get('date')}] model={m.get('model')} "
                  f"res_id={m.get('res_id')} — {body_preview!r}")

    def _print_deleted_activity_sql_hints(self, activity_id, user_id):
        _section("MANUAL DB / SERVER LOG TRACING (activity already deleted)")
        print("""
  The activity row is gone from mail_activity. RPC cannot recover its history.
  Ask your DBA / ops to run on PostgreSQL (read-only):

  -- 1) Confirm deleted
  SELECT id, res_model, res_id, user_id, summary, create_date, write_date
  FROM mail_activity WHERE id = %(activity_id)s;

  -- 2) If you have table auditing / backup, restore row from backup at error time

  -- 3) Server log at error timestamp (replace date):
  grep -E 'mail.activity\\(%(activity_id)s|MissingError|does not exist' /var/log/odoo/odoo-server.log

  -- 4) Find QIL reviews for this manager around that time
  SELECT q.id, q.state, q.write_date, e.name AS employee
  FROM quality_issue_log q
  JOIN hr_employee e ON e.id = q.employee_id
  JOIN hr_employee m ON m.id = e.parent_id
  WHERE m.user_id = %(user_id)s
    AND q.state = 'reviewing'
  ORDER BY q.write_date DESC;

  -- 5) Pending approvals linked via Studio field (if column exists)
  -- Check: \\d approval_request  for x_studio_quality_issue_log
""" % {"activity_id": activity_id, "user_id": user_id or "NULL"})

    # ------------------------------------------------------------------
    # 2. Audit user — find risky situations BEFORE they error
    # ------------------------------------------------------------------

    def audit_user(self, user_id=None, login=None):
        user = self._resolve_user(user_id=user_id, login=login)
        if not user:
            raise RuntimeError(f"User not found (user_id={user_id}, login={login})")

        _section(f"USER AUDIT — {user['name']} (id={user['id']})")
        self.report["audited_user"] = {"id": user["id"], "login": user["login"], "name": user["name"]}

        self._audit_user_activities(user["id"])
        self._audit_manager_quality_logs(user["id"])
        self._audit_approval_requests_for_manager(user["id"])

    def _audit_user_activities(self, user_id):
        _section("Open activities assigned to user")
        acts = self.c.search_read(
            "mail.activity",
            [("user_id", "=", user_id)],
            fields=["id", "summary", "res_model", "res_id", "activity_type_id", "date_deadline", "create_date"],
            order="date_deadline asc",
            limit=200,
        )
        _info("Total open activities", len(acts))

        qil_acts = [a for a in acts if a["res_model"] == QIL_MODEL]
        appr_acts = [a for a in acts if a["res_model"] == APPROVAL_MODEL]
        _info("On quality.issue.log", len(qil_acts))
        _info("On approval.request", len(appr_acts))

        broken = []
        for a in acts:
            if a["res_model"] not in (QIL_MODEL, APPROVAL_MODEL):
                continue
            if not self._record_exists(a["res_model"], a["res_id"]):
                broken.append(a)
                self._add_finding(
                    "high", "activity_broken_document",
                    f"Activity {a['id']} links to missing {a['res_model']}({a['res_id']})",
                    a,
                )

        legacy = [a for a in qil_acts if a.get("summary") == LEGACY_ACTIVITY_SUMMARY]
        if legacy and appr_acts:
            self._add_finding(
                "medium", "dual_workflow",
                "User has BOTH legacy QIL To-Do AND approval.request activities — "
                "high risk of Missing Record if one path deletes the other",
                {"legacy_activity_ids": [a["id"] for a in legacy],
                 "approval_activity_ids": [a["id"] for a in appr_acts]},
            )

        if not broken and not (legacy and appr_acts):
            _ok("No broken QIL/approval activities detected for this user right now")

    def _audit_manager_quality_logs(self, manager_user_id):
        _section("Quality issue logs where user is employee manager")

        # Employees managed by this user
        managed = self.c.search_read(
            "hr.employee",
            [("parent_id.user_id", "=", manager_user_id)],
            fields=["id", "name"],
            limit=500,
        )
        if not managed:
            _info("Managed employees", 0)
            return

        emp_ids = [e["id"] for e in managed]
        logs = self.c.search_read(
            QIL_MODEL,
            [("employee_id", "in", emp_ids)],
            fields=["id", "display_name", "state", "employee_id", "write_date", "log_type"],
            order="write_date desc",
            limit=100,
        )
        reviewing = [l for l in logs if l["state"] == "reviewing"]
        _info("Reviewing logs", len(reviewing))

        link_field = self._qil_link_field_on_approval()

        for log in reviewing:
            log_id = log["id"]
            issues = {}

            # Activities on this QIL for any user
            qil_activities = self.c.search_read(
                "mail.activity",
                [("res_model", "=", QIL_MODEL), ("res_id", "=", log_id)],
                fields=["id", "user_id", "summary"],
            )
            issues["qil_activity_count"] = len(qil_activities)
            issues["qil_activity_ids"] = [a["id"] for a in qil_activities]

            # Linked approval request
            approval = None
            if link_field and self._model_available(APPROVAL_MODEL):
                approvals = self.c.search_read(
                    APPROVAL_MODEL,
                    [(link_field, "=", log_id)],
                    fields=["id", "request_status", "name"],
                    limit=1,
                )
                approval = approvals[0] if approvals else None

            if approval:
                issues["approval_id"] = approval["id"]
                issues["approval_status"] = approval["request_status"]

                appr_activities = self.c.search(
                    "mail.activity",
                    [("res_model", "=", APPROVAL_MODEL), ("res_id", "=", approval["id"])],
                )
                issues["approval_activity_count"] = len(appr_activities)

                if approval["request_status"] in ("approved", "refused", "cancel"):
                    self._add_finding(
                        "high", "qil_stuck_reviewing",
                        f"QIL {log_id} still 'reviewing' but approval {approval['id']} "
                        f"is '{approval['request_status']}' — user may click stale activity",
                        {"quality_log": log, "approval": approval},
                    )
                elif not appr_activities and approval["request_status"] == "pending":
                    self._add_finding(
                        "medium", "pending_approval_no_activity",
                        f"Approval {approval['id']} is pending but has NO open activity",
                        {"quality_log": log, "approval": approval},
                    )
            else:
                if not qil_activities:
                    self._add_finding(
                        "medium", "reviewing_no_activity_no_approval",
                        f"QIL {log_id} is 'reviewing' with no activity and no linked approval",
                        log,
                    )
                elif all(a.get("summary") == LEGACY_ACTIVITY_SUMMARY for a in qil_activities):
                    self._add_finding(
                        "low", "legacy_only_review",
                        f"QIL {log_id} uses legacy To-Do only (no approval.request linked)",
                        {"log_id": log_id, "activities": qil_activities},
                    )

            self.report["risky_records"].append({"quality_log_id": log_id, **issues})

    def _audit_approval_requests_for_manager(self, manager_user_id):
        if not self._model_available(APPROVAL_MODEL):
            return

        _section("Approval requests where user is approver")

        approver_lines = self.c.search_read(
            "approval.approver",
            [("user_id", "=", manager_user_id), ("status", "in", ["pending", "waiting"])],
            fields=["id", "request_id", "status"],
            limit=100,
        )
        _info("Pending/waiting approver lines", len(approver_lines))

        approval_type_id = self._approval_activity_type_id()
        for line in approver_lines:
            req_id = line["request_id"][0]
            approval = self.c.read(
                APPROVAL_MODEL, [req_id],
                fields=["id", "name", "request_status"],
            )[0]

            activity_domain = [
                ("res_model", "=", APPROVAL_MODEL),
                ("res_id", "=", req_id),
                ("user_id", "=", manager_user_id),
            ]
            if approval_type_id:
                activity_domain.append(("activity_type_id", "=", approval_type_id))

            act_ids = self.c.search("mail.activity", activity_domain)
            if not act_ids and line["status"] == "pending":
                self._add_finding(
                    "medium", "approver_pending_no_activity",
                    f"User is pending approver on approval {req_id} "
                    f"but has no matching mail.activity — may have been deleted",
                    {"approval": approval, "approver_line": line},
                )
            elif act_ids:
                _ok(f"Approval {req_id}: activity {act_ids} present for pending approver")

    # ------------------------------------------------------------------
    # 3. Search ir.logging for historical errors
    # ------------------------------------------------------------------

    def search_error_logs(self, days=14, user_id=None, activity_id=None):
        if not self._model_available("ir.logging"):
            _warn("ir.logging model not available")
            return

        _section(f"ir.logging search (last {days} days)")
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        domain = [
            ("create_date", ">=", since),
            "|", "|", "|",
            ("message", "ilike", "does not exist"),
            ("message", "ilike", "Missing"),
            ("message", "ilike", "mail.activity"),
            ("message", "ilike", "Review Quality Issue"),
        ]
        if user_id:
            domain = ["&"] + domain + [("message", "ilike", str(user_id))]
        if activity_id:
            domain = ["&"] + domain + [("message", "ilike", str(activity_id))]

        logs = self.c.search_read(
            "ir.logging", domain,
            fields=["id", "name", "level", "path", "message", "func", "line", "create_date"],
            order="create_date desc",
            limit=50,
        )

        if not logs:
            _warn(
                "No matching ir.logging entries. DB logging is often DISABLED in production. "
                "Enable in odoo.conf: log_handler = :INFO,odoo.http.rpc.request:DEBUG "
                "and log_db = True (or grep server log files directly)."
            )
            self._add_finding(
                "info", "no_db_logs",
                "ir.logging has no matching entries — use server log files for historical trace",
            )
            return

        _info("Matching log entries", len(logs))
        self.report["log_entries"] = logs
        for row in logs:
            print(f"\n  [{row.get('create_date')}] {row.get('level')} {row.get('name')}")
            print(f"    {row.get('path')}:{row.get('line')} in {row.get('func')}")
            msg = (row.get("message") or "")[:500]
            print(f"    {msg}")

    # ------------------------------------------------------------------
    # 4. Module-specific workflow summary
    # ------------------------------------------------------------------

    def print_module_risk_summary(self):
        _section("MODULE RISK SUMMARY (cap_quality_issue_log current code)")
        print("""
  Current production code paths that cause mail.activity Missing Record:

  1. ask_for_review() creates a legacy To-Do on quality.issue.log
     (summary='Review Quality Issue'), NOT on approval.request.

  2. If approval.request is also used (Studio field x_studio_quality_issue_log),
     the manager may have TWO notification types for the same review.

  3. When approval is approved/refused, Odoo Approvals DELETES the activity
     (_cancel_activities / action_feedback). Browser systray can keep the old id.

  4. accept_review / refuse_review on quality.issue.log do NOT touch activities
     or approval.request — so state and activities can diverge.

  5. The error is CLIENT-TIMING sensitive: refresh the page and it disappears.
     That is why UI testing often cannot reproduce it.

  RECOMMENDED when error is reported:
  - Note exact time + user id + activity id from popup
  - Run this script immediately with --activity-id and --user-id
  - Ask user: Did they use systray/bell notification vs open the form fresh?
  - Check if they clicked Approve twice or used both QIL buttons and approval form
""")

    def run(
        self,
        user_id=None,
        login=None,
        activity_id=None,
        search_logs=False,
        log_days=14,
        reproduce=True,
        code_path=True,
    ):
        if activity_id:
            self.investigate_activity_id(
                activity_id,
                user_id=user_id,
                reproduce=reproduce,
                code_path=code_path,
            )

        if user_id or login:
            self.audit_user(user_id=user_id, login=login)

        if not activity_id and not user_id and not login:
            _warn("Provide --user-id or --login and/or --activity-id")
            self.print_module_risk_summary()
            return self.report

        if search_logs:
            self.search_error_logs(days=log_days, user_id=user_id, activity_id=activity_id)

        if not code_path:
            pass
        elif activity_id and self.report.get("code_traces"):
            pass  # already printed during investigate
        elif user_id or login:
            _section("CODE PATH REFERENCE (both workflows)")
            self.print_code_path("approval_request")
            self.print_code_path("qil_legacy_todo")

        self.print_module_risk_summary()

        _section("TRACE COMPLETE")
        high = sum(1 for f in self.report["findings"] if f["severity"] == "high")
        med = sum(1 for f in self.report["findings"] if f["severity"] == "medium")
        _info("High severity findings", high)
        _info("Medium severity findings", med)

        if self.report.get("reproduce"):
            repro = self.report["reproduce"]
            if any(r.get("reproduced") for r in repro.values()):
                _ok("Missing Record reproduced via RPC — see 'reproduce' section in JSON report")

        if high:
            _warn("High-risk mismatches found — users may hit Missing Record on next click")
        else:
            _ok("No high-risk issues in current DB state (error may have been transient/stale UI)")

        return self.report


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Trace mail.activity Missing Record errors for cap_quality_issue_log",
    )
    p.add_argument("--url", default=os.environ.get("ODOO_URL", "http://localhost:8069"))
    p.add_argument("--db", default=os.environ.get("ODOO_DB"), required=not os.environ.get("ODOO_DB"))
    p.add_argument("--user", default=os.environ.get("ODOO_USER", "admin"))
    p.add_argument("--password", default=os.environ.get("ODOO_PASSWORD", "admin"))
    p.add_argument("--rpc", choices=["xmlrpc", "jsonrpc"], default=os.environ.get("ODOO_RPC", "xmlrpc"))

    p.add_argument("--user-id", type=int, default=None, help="Affected user id from error (e.g. 42)")
    p.add_argument("--login", default=None, help="Affected user login (alternative to --user-id)")
    p.add_argument("--activity-id", type=int, default=None, help="mail.activity id from error (e.g. 1743636)")

    p.add_argument("--search-logs", action="store_true", help="Search ir.logging table")
    p.add_argument("--log-days", type=int, default=14, help="Days of logs to search (default 14)")
    p.add_argument("--output", default=None, help="Write JSON report to this file")
    p.add_argument(
        "--no-reproduce",
        action="store_true",
        help="Skip RPC reproduce step (mail.activity read/action_feedback on deleted id)",
    )
    p.add_argument(
        "--no-code-path",
        action="store_true",
        help="Skip code path mapping to module files",
    )

    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if not args.db:
        print("Error: --db required", file=sys.stderr)
        return 1

    if not args.user_id and not args.login and not args.activity_id:
        print(
            "Tip: pass --user-id 42 --activity-id 1743636 from the error message\n",
            file=sys.stderr,
        )

    try:
        client = connect(args.url, args.db, args.user, args.password, rpc=args.rpc)
        tracer = MailActivityTracer(client)
        report = tracer.run(
            user_id=args.user_id,
            login=args.login,
            activity_id=args.activity_id,
            search_logs=args.search_logs,
            log_days=args.log_days,
            reproduce=not args.no_reproduce,
            code_path=not args.no_code_path,
        )
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, default=str)
            print(f"\nJSON report written to {args.output}")

    except RpcError as exc:
        print(f"\nRPC Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
