#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone RPC / HTTP test for connect_mistral_ai (Odoo 19).

Uses an **existing** ai.agent with a Mistral LLM model (does not create agents).
Pass --agent-id to pin a specific agent, or the newest Mistral agent in the DB is used.

No odoo-bin / shell required. Run with plain Python 3:

    python3 models/test_connect_mistral_ai_rpc.py
    python3 models/test_connect_mistral_ai_rpc.py --url http://localhost:8069 --db odoo --user admin --password admin

Live Mistral API tests (requires API key in Odoo or --mistral-key):

    python3 models/test_connect_mistral_ai_rpc.py --live
    python3 models/test_connect_mistral_ai_rpc.py --live --mistral-key "$MISTRAL_API_KEY"

Custom prompt + context:

    python3 models/test_connect_mistral_ai_rpc.py --live --custom-only \\
        --prompt "What is the project deadline?" \\
        --context "The project deadline is June 30, 2026." \\
        --expect "June 30"

Via test automation suite:

    python3 test_automation/run_test_suite.py --scenario connect_mistral_ai \\
        --url ... --db ... --user ... --password ...
"""
from __future__ import annotations

import argparse
import base64
import http.cookiejar
import json
import os
import sys
import time
import xmlrpc.client
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

DEFAULT_URL = os.environ.get("ODOO_URL", "http://localhost:8069")
DEFAULT_DB = os.environ.get("ODOO_DB", "odoo")
DEFAULT_USER = os.environ.get("ODOO_USER", "admin")
DEFAULT_PASSWORD = os.environ.get("ODOO_PASSWORD", "admin")
DEFAULT_PROTOCOL = os.environ.get("ODOO_RPC", "jsonrpc")

MODULE_NAME = "connect_mistral_ai"
DEPENDENCY_MODULES = ("ai", "ai_app")
PARAM_MISTRAL_KEY = "connect_mistral_ai.mistral_key"

MODEL_CONFIG_SETTINGS = "res.config.settings"
FIELD_MISTRAL_KEY = "mistral_key"
FIELD_MISTRAL_KEY_ENABLED = "mistral_key_enabled"

MODEL_AI_AGENT = "ai.agent"
MODEL_AI_AGENT_SOURCE = "ai.agent.source"
MODEL_AI_EMBEDDING = "ai.embedding"
MODEL_IR_CONFIG = "ir.config_parameter"
MODEL_IR_CRON = "ir.cron"
MODEL_IR_MODEL_DATA = "ir.model.data"

FIELD_AGENT_LLM_MODEL = "llm_model"
FIELD_AGENT_RESPONSE_STYLE = "response_style"
FIELD_EMBEDDING_MODEL = "embedding_model"

MISTRAL_LLM_MODELS = (
    "mistral-small-latest",
    "mistral-medium-latest",
    "mistral-large-latest",
)
MISTRAL_EMBEDDING_MODEL = "mistral-embed"
DEFAULT_LIVE_LLM = "mistral-small-latest"

ROUTE_TRANSCRIPTION_SESSION = "/ai/transcription/session"
ROUTE_TRANSCRIPTION_AUDIO = "/ai/transcription/audio"

CTX_SECRET_TOKEN = "RPC-MISTRAL-CTX-8842"
RAG_SECRET_CODE = "SECRET-MISTRAL-RPC-42"


@dataclass
class CustomScenario:
    prompt: str | None = None
    context: str | None = None
    context_file: str | None = None
    expect: list[str] = field(default_factory=list)
    rag_text: str | None = None
    rag_file: str | None = None
    agent_id: int | None = None
    llm_model: str = DEFAULT_LIVE_LLM
    custom_only: bool = False
    print_response: bool = False

    def has_direct(self) -> bool:
        return bool(self.prompt and not self.rag_payload())

    def has_rag(self) -> bool:
        return bool(self.prompt and self.rag_payload())

    def rag_payload(self) -> bytes | None:
        if self.rag_text:
            return self.rag_text.encode("utf-8")
        if self.rag_file:
            return Path(self.rag_file).read_bytes()
        return None

    def resolved_context(self) -> str:
        if self.context_file:
            return Path(self.context_file).read_text(encoding="utf-8")
        return self.context or ""


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
            if not uid:
                raise RuntimeError("Authentication failed.")
            self.uid = uid
            return uid

        uid = self._jsonrpc(
            "common", "authenticate", [self.db, self.username, self.password, {}]
        )
        if not uid:
            raise RuntimeError("Authentication failed.")
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
        self, model: str, method: str, args: list | None = None, kwargs: dict | None = None
    ) -> Any:
        if self.uid is None:
            raise RuntimeError("Not authenticated.")
        args = args or []
        kwargs = kwargs or {}
        if self.protocol == "xmlrpc":
            return self._xml_models.execute_kw(
                self.db, self.uid, self.password, model, method, args, kwargs
            )
        return self._jsonrpc(
            "object", "execute_kw", [self.db, self.uid, self.password, model, method, args, kwargs]
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

    def unlink(self, model: str, ids: list[int]) -> bool:
        return self.execute_kw(model, "unlink", [ids])

    def fields_get(self, model: str, fields: list[str] | None = None, **kwargs: Any) -> dict:
        return self.execute_kw(model, "fields_get", [fields or []], kwargs)


class OdooHTTPClient:
    def __init__(self, url: str, db: str, username: str, password: str):
        self.url = url.rstrip("/")
        self._json_id = 0
        self._cookie_jar = http.cookiejar.CookieJar()
        self._opener = build_opener(HTTPCookieProcessor(self._cookie_jar))
        self._jsonrpc_call(
            "/web/session/authenticate",
            {"db": db, "login": username, "password": password},
        )

    def _jsonrpc_call(self, path: str, params: dict) -> Any:
        self._json_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": params,
            "id": self._json_id,
        }
        req = Request(
            f"{self.url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self._opener.open(req, timeout=180) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        if body.get("error"):
            err = body["error"]
            msg = err.get("data", {}).get("message") or err.get("message") or str(err)
            raise RuntimeError(f"HTTP JSON-RPC error on {path}: {msg}")
        return body.get("result")

    def call_controller_jsonrpc(self, route: str, params: dict | None = None) -> Any:
        return self._jsonrpc_call(route, params or {})

    def post_binary(self, route: str, data: bytes, content_type: str) -> tuple[int, dict | str]:
        req = Request(
            f"{self.url}{route}",
            data=data,
            headers={"Content-Type": content_type},
            method="POST",
        )
        try:
            with self._opener.open(req, timeout=180) as resp:
                status = resp.status
                raw = resp.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            status = exc.code
            raw = exc.read().decode("utf-8", errors="replace")
        try:
            return status, json.loads(raw)
        except json.JSONDecodeError:
            return status, raw


class ConnectMistralAIRPCTest:
    def __init__(
        self,
        client: OdooRPCClient,
        *,
        live: bool = False,
        mistral_key: str | None = None,
        rag_timeout: int = 180,
        http_client: OdooHTTPClient | None = None,
        custom: CustomScenario | None = None,
    ):
        self.client = client
        self.live = live
        self.mistral_key = mistral_key
        self.rag_timeout = rag_timeout
        self.http = http_client
        self.custom = custom or CustomScenario()
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self._saved_mistral_key: str | False = False
        self._agent_id_cache: int | None = None

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

    def _module_installed(self, name: str) -> bool:
        return bool(
            self.client.search(
                "ir.module.module",
                [("name", "=", name), ("state", "=", "installed")],
            )
        )

    def _selection_keys(self, model: str, field_name: str) -> set[str]:
        meta = self.client.fields_get(model, [field_name])
        return {key for key, _label in (meta.get(field_name) or {}).get("selection") or []}

    def _get_config_param(self, key: str) -> str | False:
        return self.client.execute_kw(MODEL_IR_CONFIG, "get_param", [key])

    def _set_config_param(self, key: str, value: str) -> bool:
        return self.client.execute_kw(MODEL_IR_CONFIG, "set_param", [key, value])

    def _find_existing_mistral_agent(self) -> int | None:
        if self._agent_id_cache is not None:
            return self._agent_id_cache
        if self.custom.agent_id:
            self._agent_id_cache = self.custom.agent_id
            return self._agent_id_cache
        ids = self.client.search(
            MODEL_AI_AGENT,
            [(FIELD_AGENT_LLM_MODEL, "in", list(MISTRAL_LLM_MODELS))],
            limit=1,
            order="id desc",
        )
        self._agent_id_cache = ids[0] if ids else None
        return self._agent_id_cache

    def _require_existing_mistral_agent(self, label: str) -> int | None:
        agent_id = self._find_existing_mistral_agent()
        if not agent_id:
            self._ok(
                label,
                False,
                "no ai.agent found — create one in Odoo or pass --agent-id",
            )
            return None
        try:
            self.client.read(MODEL_AI_AGENT, [agent_id], ["id", "name", FIELD_AGENT_LLM_MODEL])
        except RuntimeError as exc:
            if self._rpc_access_denied(exc):
                self._ok(label, False, f"no read access to ai.agent id={agent_id}")
                return None
            raise
        return agent_id

    def _response_text(self, response: Any) -> str:
        if isinstance(response, list):
            return " ".join(str(part) for part in response if part)
        return str(response or "")

    def _backup_and_set_mistral_key(self, key: str | None) -> None:
        self._saved_mistral_key = self._get_config_param(PARAM_MISTRAL_KEY)
        if key is not None:
            self._set_config_param(PARAM_MISTRAL_KEY, key)

    def _restore_mistral_key(self) -> None:
        if self._saved_mistral_key is False:
            return
        self._set_config_param(PARAM_MISTRAL_KEY, self._saved_mistral_key or "")

    def _rpc_access_denied(self, exc: BaseException) -> bool:
        msg = str(exc).lower()
        return "not allowed" in msg or "access" in msg

    def _is_admin_smoke_user(self) -> bool:
        try:
            self.client.search("ir.module.module", [("name", "=", MODULE_NAME)], limit=1)
        except RuntimeError as exc:
            if self._rpc_access_denied(exc):
                return False
            raise
        try:
            self._get_config_param(PARAM_MISTRAL_KEY)
            return True
        except RuntimeError as exc:
            if self._rpc_access_denied(exc):
                return False
            raise

    def _run_role_user_tests(self) -> None:
        """Role user uses server-side Mistral key — no Settings / ir.config_parameter access needed."""
        print("\n--- Role user — global Mistral key (server-side, not in Settings UI) ---")
        agent_id = self._require_existing_mistral_agent("can access existing ai.agent")
        if not agent_id:
            return
        try:
            agent = self.client.read(
                MODEL_AI_AGENT, [agent_id], ["name", FIELD_AGENT_LLM_MODEL]
            )[0]
            self._ok(
                "can read ai.agent",
                True,
                f"id={agent_id} model={agent.get(FIELD_AGENT_LLM_MODEL)!r}",
            )
        except RuntimeError as exc:
            self._ok("can read ai.agent", False, str(exc)[:120])
            return

        if not self.live:
            return

        try:
            response = self.client.execute_kw(
                MODEL_AI_AGENT,
                "get_direct_response",
                [[agent_id], "Say hi in one word", ""],
            )
            text = self._response_text(response)
            self._ok(
                "live Mistral via global key (get_direct_response)",
                bool(text.strip()),
                text[:160],
            )
        except RuntimeError as exc:
            msg = str(exc)
            if "No API key set for Mistral" in msg:
                detail = "admin must set connect_mistral_ai.mistral_key once (users need not see Settings)"
            else:
                detail = msg[:200]
            self._ok("live Mistral via global key (get_direct_response)", False, detail)

    def _ensure_live_ready(self) -> None:
        if self.custom.prompt or self.custom.rag_payload():
            self.live = True
        if not self.live:
            return
        if not self._is_admin_smoke_user():
            return
        current_key = self._get_config_param(PARAM_MISTRAL_KEY)
        if self.mistral_key:
            self._backup_and_set_mistral_key(self.mistral_key)
        elif current_key:
            self.mistral_key = str(current_key)
        else:
            self._skip(
                "Live / custom AI tests",
                "no Mistral API key in Odoo and none passed via --mistral-key",
            )
            self.live = False

    def _run_structural_tests(self) -> None:
        print("\n--- Structural / configuration ---")
        self._ok(f"Module {MODULE_NAME!r} installed", self._module_installed(MODULE_NAME))
        for dep in DEPENDENCY_MODULES:
            self._ok(f"Dependency {dep!r} installed", self._module_installed(dep))

        llm_selection = self._selection_keys(MODEL_AI_AGENT, FIELD_AGENT_LLM_MODEL)
        for model_name in MISTRAL_LLM_MODELS:
            self._ok(
                f"{MODEL_AI_AGENT}.{FIELD_AGENT_LLM_MODEL} includes {model_name!r}",
                model_name in llm_selection,
            )

        embed_selection = self._selection_keys(MODEL_AI_EMBEDDING, FIELD_EMBEDDING_MODEL)
        self._ok(
            f"{MODEL_AI_EMBEDDING}.{FIELD_EMBEDDING_MODEL} includes {MISTRAL_EMBEDDING_MODEL!r}",
            MISTRAL_EMBEDDING_MODEL in embed_selection,
        )

        settings_fields = self.client.fields_get(
            MODEL_CONFIG_SETTINGS,
            [FIELD_MISTRAL_KEY, FIELD_MISTRAL_KEY_ENABLED],
        )
        self._ok(
            f"{MODEL_CONFIG_SETTINGS}.{FIELD_MISTRAL_KEY} exists",
            FIELD_MISTRAL_KEY in settings_fields,
        )
        self._ok(
            f"{MODEL_CONFIG_SETTINGS}.{FIELD_MISTRAL_KEY_ENABLED} exists",
            FIELD_MISTRAL_KEY_ENABLED in settings_fields,
        )

        agent_id = self._require_existing_mistral_agent(f"{MODEL_AI_AGENT} uses Mistral LLM model")
        if not agent_id:
            return
        agent = self.client.read(
            MODEL_AI_AGENT, [agent_id], [FIELD_AGENT_LLM_MODEL, "name"]
        )[0]
        self._ok(
            f"{MODEL_AI_AGENT} uses Mistral LLM model",
            agent[FIELD_AGENT_LLM_MODEL] in MISTRAL_LLM_MODELS,
            f"id={agent_id} model={agent[FIELD_AGENT_LLM_MODEL]!r}",
        )

    def _run_config_tests(self) -> None:
        print("\n--- API key configuration ---")
        test_key = "rpc-test-mistral-key-placeholder"
        self._backup_and_set_mistral_key(test_key)
        try:
            stored = self._get_config_param(PARAM_MISTRAL_KEY)
            self._ok(
                f"{PARAM_MISTRAL_KEY} persists via ir.config_parameter",
                stored == test_key,
                f"got {stored!r}",
            )
        finally:
            self._restore_mistral_key()

    def _run_missing_key_test(self) -> None:
        print("\n--- Missing API key guard ---")
        agent_id = self._require_existing_mistral_agent("existing agent for missing-key guard")
        if not agent_id:
            return
        self._backup_and_set_mistral_key("")
        try:
            try:
                self.client.execute_kw(
                    MODEL_AI_AGENT,
                    "get_direct_response",
                    [[agent_id], "Hello", ""],
                )
                self._ok(
                    "get_direct_response fails without Mistral API key",
                    False,
                    "expected UserError but call succeeded",
                )
            except RuntimeError as exc:
                self._ok(
                    "get_direct_response fails without Mistral API key",
                    "No API key set for Mistral" in str(exc),
                    str(exc)[:120],
                )
        finally:
            self._restore_mistral_key()
            if self.live and self.mistral_key:
                self._set_config_param(PARAM_MISTRAL_KEY, self.mistral_key)

    def _apply_live_mistral_key(self) -> None:
        if self.live and self.mistral_key:
            self._set_config_param(PARAM_MISTRAL_KEY, self.mistral_key)

    def _run_live_context_tests(self) -> None:
        if not self.live:
            return
        self._apply_live_mistral_key()
        print("\n--- Live context injection (get_direct_response) ---")
        agent_id = self._require_existing_mistral_agent("existing agent for context test")
        if not agent_id:
            return
        context_message = (
            "Use only this context. The project deadline is June 30, 2026. "
            f"Secret token: {CTX_SECRET_TOKEN}."
        )
        prompt = "What is the project deadline? Answer briefly using only the provided context."
        try:
            response = self.client.execute_kw(
                MODEL_AI_AGENT,
                "get_direct_response",
                [[agent_id], prompt, context_message],
            )
            text = self._response_text(response).lower()
            self._ok(
                "TC-CTX-01 injected context used for deadline",
                "june 30" in text or "2026-06-30" in text or "30 june" in text,
                self._response_text(response)[:160],
            )
        except RuntimeError as exc:
            self._ok("Live context injection", False, str(exc)[:200])

    def _run_live_chat_style_tests(self) -> None:
        if not self.live:
            return
        print("\n--- Live chat style ---")
        agent_id = self._require_existing_mistral_agent("existing agent for chat test")
        if not agent_id:
            return
        try:
            response = self.client.execute_kw(
                MODEL_AI_AGENT,
                "get_direct_response",
                [[agent_id], "hey", ""],
            )
            text = self._response_text(response)
            self._ok("TC-CHAT-01 greeting returns non-empty reply", bool(text.strip()), text[:160])
        except RuntimeError as exc:
            self._ok("Live chat style", False, str(exc)[:200])

    def _trigger_embedding_cron(self) -> bool:
        rows = self.client.execute_kw(
            MODEL_IR_MODEL_DATA,
            "search_read",
            [[("module", "=", "ai"), ("name", "=", "ir_cron_generate_embedding")]],
            {"fields": ["res_id"], "limit": 1},
        )
        if not rows:
            return False
        self.client.execute_kw(MODEL_IR_CRON, "method_direct_trigger", [[rows[0]["res_id"]]])
        return True

    def _wait_for_source_indexed(self, source_id: int) -> bool:
        deadline = time.time() + self.rag_timeout
        while time.time() < deadline:
            row = self.client.read(
                MODEL_AI_AGENT_SOURCE,
                [source_id],
                ["status", "is_active", "error_details"],
            )[0]
            if row.get("status") == "indexed" and row.get("is_active"):
                return True
            if row.get("status") == "failed":
                raise RuntimeError(row.get("error_details") or "RAG indexing failed")
            self._trigger_embedding_cron()
            time.sleep(4)
        return False

    def _run_custom_direct_test(self) -> None:
        if not self.custom.has_direct() or not self.live:
            return
        print("\n--- Custom prompt + context ---")
        agent_id = self._require_existing_mistral_agent("existing agent for custom prompt")
        if not agent_id:
            return
        context_message = self.custom.resolved_context()
        prompt = self.custom.prompt or ""
        response = self.client.execute_kw(
            MODEL_AI_AGENT,
            "get_direct_response",
            [[agent_id], prompt, context_message],
        )
        text = self._response_text(response)
        if self.custom.print_response:
            print(f"\n--- AI response ---\n{text}\n--- end ---\n")
        if self.custom.expect:
            lowered = text.lower()
            for needle in self.custom.expect:
                self._ok(f"response contains {needle!r}", needle.lower() in lowered, text[:160])
        else:
            self._ok("custom prompt returned a response", bool(text.strip()), text[:160])

    def _run_custom_rag_test(self) -> None:
        if not self.custom.has_rag() or not self.live:
            return
        print("\n--- Custom RAG ---")
        agent_id = self._require_existing_mistral_agent("existing agent for custom RAG")
        if not agent_id:
            return
        payload = self.custom.rag_payload()
        assert payload is not None
        files = [
            {
                "name": "rpc_mistral_rag.txt",
                "datas": base64.b64encode(payload).decode("ascii"),
                "mimetype": "text/plain",
            }
        ]
        source_ids = self.client.execute_kw(
            MODEL_AI_AGENT_SOURCE,
            "create_from_binary_files",
            [files, agent_id],
        )
        if not source_ids:
            self._ok("RAG source created", False)
            return
        self._ok("RAG source created", self._wait_for_source_indexed(source_ids[0]))
        response = self.client.execute_kw(
            MODEL_AI_AGENT,
            "get_direct_response",
            [[agent_id], self.custom.prompt, ""],
        )
        text = self._response_text(response)
        if self.custom.expect:
            lowered = text.lower()
            for needle in self.custom.expect:
                self._ok(f"RAG response contains {needle!r}", needle.lower() in lowered, text[:160])
        else:
            self._ok("RAG prompt returned a response", bool(text.strip()), text[:160])

    def _run_http_transcription_tests(self) -> None:
        if not self.live or not self.http:
            if self.live and not self.http:
                self._skip("HTTP transcription tests", "HTTP session client not initialized")
            return
        print("\n--- HTTP transcription controller ---")
        session_result = self.http.call_controller_jsonrpc(
            ROUTE_TRANSCRIPTION_SESSION, {"language": "en"}
        )
        self._ok(
            "TC-HTTP-01 /ai/transcription/session responds",
            isinstance(session_result, dict),
            str(session_result)[:120],
        )
        status, _body = self.http.post_binary(ROUTE_TRANSCRIPTION_AUDIO, b"", "audio/webm")
        self._ok("TC-HTTP-02 empty audio rejected", status == 400, f"status={status}")

    def run(self) -> bool:
        has_custom = self.custom.has_direct() or self.custom.has_rag()
        role_user = not self._is_admin_smoke_user()
        mode = "SMOKE (no external API calls)"
        if self.custom.custom_only and has_custom:
            mode = "CUSTOM"
        elif role_user and self.live:
            mode = "ROLE USER LIVE (Mistral API)"
        elif role_user:
            mode = "ROLE USER SMOKE"
        elif self.live:
            mode = "LIVE (Mistral API)"

        print("=" * 80)
        print("Mistral AI Connector — RPC / HTTP Test (Odoo 19)")
        print(f"Module : {MODULE_NAME}")
        print(f"DB     : {self.client.db} | URL: {self.client.url}")
        print(f"User   : uid={self.client.uid}")
        print(f"Mode   : {mode}")
        print("=" * 80)

        try:
            self._ensure_live_ready()
            run_builtin = not self.custom.custom_only

            if run_builtin:
                if role_user:
                    self._run_role_user_tests()
                else:
                    self._run_structural_tests()
                    if self.live and self.mistral_key:
                        self._apply_live_mistral_key()
                    else:
                        self._run_config_tests()
                        self._run_missing_key_test()
                        if self.live and self.mistral_key:
                            self._apply_live_mistral_key()

            if has_custom:
                if self.custom.has_rag():
                    self._run_custom_rag_test()
                else:
                    self._run_custom_direct_test()

            if run_builtin and self.live and not role_user:
                self._run_live_context_tests()
                self._run_live_chat_style_tests()
                self._run_http_transcription_tests()
        finally:
            self._restore_mistral_key()

        print("=" * 80)
        print(f"Result: {self.passed} passed, {self.failed} failed, {self.skipped} skipped")
        print("=" * 80)
        return self.failed == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RPC test for connect_mistral_ai (Odoo 19)")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--protocol", choices=["jsonrpc", "xmlrpc"], default=DEFAULT_PROTOCOL)
    parser.add_argument("--live", action="store_true", help="Run live Mistral API tests")
    parser.add_argument("--mistral-key", default=None, help="Mistral API key for live tests")
    parser.add_argument("--rag-timeout", type=int, default=180)
    custom = parser.add_argument_group("custom scenario")
    custom.add_argument("--prompt")
    custom.add_argument("--context")
    custom.add_argument("--context-file")
    custom.add_argument("--expect", action="append", default=[])
    custom.add_argument("--rag-text")
    custom.add_argument("--rag-file")
    custom.add_argument("--agent-id", type=int, default=None)
    custom.add_argument("--llm-model", default=DEFAULT_LIVE_LLM)
    custom.add_argument("--custom-only", action="store_true")
    custom.add_argument("--print-response", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    custom = CustomScenario(
        prompt=args.prompt,
        context=args.context,
        context_file=args.context_file,
        expect=list(args.expect or []),
        rag_text=args.rag_text,
        rag_file=args.rag_file,
        agent_id=args.agent_id,
        llm_model=args.llm_model,
        custom_only=args.custom_only,
        print_response=args.print_response,
    )

    client = OdooRPCClient(args.url, args.db, args.user, args.password, args.protocol)
    try:
        uid = client.authenticate()
        print(f"Authenticated uid={uid}")
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    live = args.live or custom.has_direct() or custom.has_rag()
    http_client = None
    if live:
        try:
            http_client = OdooHTTPClient(args.url, args.db, args.user, args.password)
        except RuntimeError as exc:
            print(f"WARN: HTTP session auth failed: {exc}", file=sys.stderr)

    ok = ConnectMistralAIRPCTest(
        client,
        live=live,
        mistral_key=args.mistral_key,
        rag_timeout=args.rag_timeout,
        http_client=http_client,
        custom=custom,
    ).run()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
