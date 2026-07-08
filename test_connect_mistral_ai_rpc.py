#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone RPC / HTTP test for connect_mistral_ai (Odoo 19).

No odoo-bin / shell required. Run with plain Python 3:

    python3 models/test_connect_mistral_ai_rpc.py
    python3 models/test_connect_mistral_ai_rpc.py --protocol xmlrpc
    python3 models/test_connect_mistral_ai_rpc.py --url http://localhost:8069 --db odoo --user admin --password admin

Live Mistral AI automation (requires valid API key in Odoo or via --mistral-key):

    python3 models/test_connect_mistral_ai_rpc.py --live
    python3 models/test_connect_mistral_ai_rpc.py --live --mistral-key "$MISTRAL_API_KEY"

Custom prompt + context (your own QA scenario):

    python3 models/test_connect_mistral_ai_rpc.py --live --custom-only \\
        --prompt "What is the project deadline?" \\
        --context "The project deadline is June 30, 2026. Use only this context." \\
        --expect "June 30" --expect "2026"

    python3 models/test_connect_mistral_ai_rpc.py --live --custom-only \\
        --context-file ./my_context.txt \\
        --prompt "Summarize the key facts." \\
        --print-response

Custom RAG document + question:

    python3 models/test_connect_mistral_ai_rpc.py --live --custom-only \\
        --rag-text "Vault code: ALPHA-99. Authorized staff only." \\
        --prompt "What is the vault code?" \\
        --expect "ALPHA-99"

Tests module wiring, configuration, model integrations, context injection, RAG sources,
and transcription HTTP endpoints using public Odoo RPC APIs and authenticated HTTP calls.

Source references:
  - models/res_config_settings.py
  - models/ai_agent.py
  - models/ai_embedding.py
  - models/models.py
  - controllers/agent.py
  - utils/llm_providers.py
"""
from __future__ import annotations

import argparse
import base64
import http.cookiejar
import json
import sys
import time
import xmlrpc.client
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

# ---------------------------------------------------------------------------
# Configuration (override via CLI args)
# ---------------------------------------------------------------------------
DEFAULT_URL = "http://localhost:8069"
DEFAULT_DB = "odoo"
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "admin"
DEFAULT_PROTOCOL = "jsonrpc"  # jsonrpc | xmlrpc

MODULE_NAME = "connect_mistral_ai"
DEPENDENCY_MODULES = ("ai", "ai_app")

# ---------------------------------------------------------------------------
# Technical names from connect_mistral_ai
# ---------------------------------------------------------------------------
PARAM_MISTRAL_KEY = "connect_mistral_ai.mistral_key"

MODEL_CONFIG_SETTINGS = "res.config.settings"
FIELD_MISTRAL_KEY = "mistral_key"
FIELD_MISTRAL_KEY_ENABLED = "mistral_key_enabled"

MODEL_AI_AGENT = "ai.agent"
MODEL_AI_AGENT_SOURCE = "ai.agent.source"
MODEL_AI_EMBEDDING = "ai.embedding"
MODEL_IR_ATTACHMENT = "ir.attachment"
MODEL_IR_CONFIG = "ir.config_parameter"
MODEL_IR_CRON = "ir.cron"
MODEL_IR_MODEL_DATA = "ir.model.data"
MODEL_RES_PARTNER = "res.partner"

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

# Unique tokens for live context / RAG assertions (unlikely to appear by chance).
CTX_SECRET_TOKEN = "RPC-CTX-DEADLINE-8842"
RAG_SECRET_CODE = "SECRET-RPC-ALPHA-42"


@dataclass
class CustomScenario:
    """User-provided live test inputs (--prompt, --context, --rag-*)."""

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

    def search_read(
        self,
        model: str,
        domain: list,
        fields: list[str],
        limit: int | None = None,
    ) -> list[dict]:
        kwargs: dict[str, Any] = {"fields": fields}
        if limit is not None:
            kwargs["limit"] = limit
        return self.execute_kw(model, "search_read", [domain], kwargs)

    def read(self, model: str, ids: list[int], fields: list[str]) -> list[dict]:
        return self.execute_kw(model, "read", [ids, fields])

    def create(self, model: str, vals: dict) -> int:
        return self.execute_kw(model, "create", [vals])

    def write(self, model: str, ids: list[int], vals: dict) -> bool:
        return self.execute_kw(model, "write", [ids, vals])

    def unlink(self, model: str, ids: list[int]) -> bool:
        return self.execute_kw(model, "unlink", [ids])

    def fields_get(self, model: str, fields: list[str] | None = None, **kwargs: Any) -> dict:
        return self.execute_kw(model, "fields_get", [fields or []], kwargs)


class OdooHTTPClient:
    """Authenticated Odoo web session client for controller routes."""

    def __init__(self, url: str, db: str, username: str, password: str):
        self.url = url.rstrip("/")
        self.db = db
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
        try:
            with self._opener.open(req, timeout=180) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"HTTP error {exc.code} on {path}: {exc.reason}") from exc
        except URLError as exc:
            raise RuntimeError(f"Cannot reach {self.url}{path}: {exc}") from exc

        if body.get("error"):
            err = body["error"]
            msg = err.get("data", {}).get("message") or err.get("message") or str(err)
            raise RuntimeError(f"Odoo HTTP JSON-RPC error on {path}: {msg}")
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
    """End-to-end connect_mistral_ai QA via RPC and HTTP."""

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
        self._cleanup_agent_ids: list[int] = []
        self._owns_agent = True

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

    def _track_agent(self, agent_id: int) -> None:
        self._cleanup_agent_ids.append(agent_id)

    def _module_installed(self, name: str) -> bool:
        return bool(
            self.client.search(
                "ir.module.module",
                [("name", "=", name), ("state", "=", "installed")],
            )
        )

    def _selection_keys(self, model: str, field_name: str) -> set[str]:
        meta = self.client.fields_get(model, [field_name])
        field = meta.get(field_name) or {}
        selection = field.get("selection") or []
        return {key for key, _label in selection}

    def _get_config_param(self, key: str) -> str | False:
        return self.client.execute_kw(MODEL_IR_CONFIG, "get_param", [key])

    def _set_config_param(self, key: str, value: str) -> bool:
        return self.client.execute_kw(MODEL_IR_CONFIG, "set_param", [key, value])

    def _backup_and_set_mistral_key(self, key: str | None) -> None:
        self._saved_mistral_key = self._get_config_param(PARAM_MISTRAL_KEY)
        if key:
            self._set_config_param(PARAM_MISTRAL_KEY, key)

    def _restore_mistral_key(self) -> None:
        if self._saved_mistral_key is False:
            return
        self._set_config_param(PARAM_MISTRAL_KEY, self._saved_mistral_key or "")

    def _resolve_agent_id(self, name: str = "RPC Custom Mistral Agent") -> int:
        if self.custom.agent_id:
            self._owns_agent = False
            rows = self.client.read(
                MODEL_AI_AGENT,
                [self.custom.agent_id],
                [FIELD_AGENT_LLM_MODEL, "name"],
            )
            if not rows:
                raise RuntimeError(f"ai.agent id={self.custom.agent_id} not found")
            return self.custom.agent_id

        return self._create_mistral_agent(
            name,
            **{FIELD_AGENT_LLM_MODEL: self.custom.llm_model},
        )

    def _create_mistral_agent(self, name: str, **extra: Any) -> int:
        vals = {
            "name": name,
            FIELD_AGENT_LLM_MODEL: self.custom.llm_model or DEFAULT_LIVE_LLM,
            FIELD_AGENT_RESPONSE_STYLE: "analytical",
        }
        vals.update(extra)
        agent_id = self.client.create(MODEL_AI_AGENT, vals)
        self._track_agent(agent_id)
        return agent_id

    def _response_text(self, response: Any) -> str:
        if isinstance(response, list):
            return " ".join(str(part) for part in response if part)
        return str(response or "")

    def _trigger_embedding_cron(self) -> bool:
        rows = self.client.search_read(
            MODEL_IR_MODEL_DATA,
            [("module", "=", "ai"), ("name", "=", "ir_cron_generate_embedding")],
            ["res_id"],
            limit=1,
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
                raise RuntimeError(row.get("error_details") or "RAG source indexing failed")
            self._trigger_embedding_cron()
            time.sleep(4)
        return False

    def _cleanup(self) -> None:
        if not self._owns_agent:
            self._cleanup_agent_ids = []
            return
        for agent_id in reversed(self._cleanup_agent_ids):
            try:
                self.client.unlink(MODEL_AI_AGENT, [agent_id])
                print(f"  Cleaned up ai.agent id={agent_id}")
            except RuntimeError as exc:
                print(f"  [WARN] cleanup ai.agent {agent_id}: {exc}")
        self._cleanup_agent_ids = []

    def _ensure_live_ready(self) -> None:
        if self.custom.prompt or self.custom.rag_payload():
            self.live = True
        if not self.live:
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

    def _assert_expectations(self, label: str, response_text: str) -> None:
        if self.custom.print_response:
            print(f"\n--- AI response ({label}) ---\n{response_text}\n--- end ---\n")
        if not self.custom.expect:
            self._ok(f"{label} returned a response", bool(response_text.strip()), response_text[:160])
            return
        lowered = response_text.lower()
        for needle in self.custom.expect:
            self._ok(
                f"{label} contains {needle!r}",
                needle.lower() in lowered,
                response_text[:160],
            )

    def _run_custom_direct_test(self) -> None:
        if not self.custom.has_direct() or not self.live:
            return

        print("\n--- Custom prompt + context (get_direct_response) ---")
        agent_id = self._resolve_agent_id()
        context_message = self.custom.resolved_context()
        prompt = self.custom.prompt or ""

        print(f"  agent_id={agent_id}")
        print(f"  prompt={prompt[:120]!r}{'...' if len(prompt) > 120 else ''}")
        if context_message:
            print(f"  context={context_message[:120]!r}{'...' if len(context_message) > 120 else ''}")

        try:
            response = self.client.execute_kw(
                MODEL_AI_AGENT,
                "get_direct_response",
                [[agent_id], prompt, context_message],
            )
            self._assert_expectations("Custom direct response", self._response_text(response))
        except RuntimeError as exc:
            self._ok("Custom direct response", False, str(exc)[:200])

    def _run_custom_rag_test(self) -> None:
        if not self.custom.has_rag() or not self.live:
            return

        print("\n--- Custom RAG document + prompt ---")
        agent_id = self._resolve_agent_id("RPC Custom RAG Agent")
        rag_body = self.custom.rag_payload()
        if not rag_body:
            return

        rag_name = Path(self.custom.rag_file).name if self.custom.rag_file else "rpc_custom_rag.txt"
        files = [
            {
                "name": rag_name,
                "datas": base64.b64encode(rag_body).decode("ascii"),
                "mimetype": "text/plain",
            }
        ]

        print(f"  agent_id={agent_id}")
        print(f"  rag_bytes={len(rag_body)}")
        print(f"  prompt={self.custom.prompt!r}")

        try:
            source_ids = self.client.execute_kw(
                MODEL_AI_AGENT_SOURCE,
                "create_from_binary_files",
                [files, agent_id],
            )
            source_id = source_ids[0] if isinstance(source_ids, list) else source_ids
            self._ok("Custom RAG source created", bool(source_id), f"source_id={source_id}")
            if not source_id:
                return

            indexed = self._wait_for_source_indexed(source_id)
            self._ok("Custom RAG source indexed", indexed, f"timeout={self.rag_timeout}s")
            if not indexed:
                return

            response = self.client.execute_kw(
                MODEL_AI_AGENT,
                "get_direct_response",
                [[agent_id], self.custom.prompt, self.custom.resolved_context()],
            )
            self._assert_expectations("Custom RAG response", self._response_text(response))
        except RuntimeError as exc:
            self._ok("Custom RAG scenario", False, str(exc)[:200])

    def _run_structural_tests(self) -> None:
        print("\n--- Structural / configuration ---")

        self._ok(
            f"Module {MODULE_NAME!r} installed",
            self._module_installed(MODULE_NAME),
        )
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

        partner_fields = self.client.fields_get(
            MODEL_RES_PARTNER,
            [],
            attributes=["ai", "string", "type"],
        )
        has_ai_field = any(meta.get("ai") for meta in partner_fields.values())
        if has_ai_field:
            self._ok("base AI fields_get exposes ai attribute", True)
        else:
            self._skip(
                "base AI fields_get exposes ai attribute on a concrete field",
                "no AI-enabled fields found on res.partner in this database",
            )

        agent_id = self._create_mistral_agent("RPC Structural Mistral Agent")
        agent = self.client.read(
            MODEL_AI_AGENT,
            [agent_id],
            [FIELD_AGENT_LLM_MODEL, "name"],
        )[0]
        self._ok(
            f"{MODEL_AI_AGENT} accepts Mistral LLM model",
            agent[FIELD_AGENT_LLM_MODEL] == DEFAULT_LIVE_LLM,
            f"id={agent_id}",
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

        current_key = self._get_config_param(PARAM_MISTRAL_KEY)
        if self.live and self.mistral_key:
            self._backup_and_set_mistral_key(self.mistral_key)
        elif self.live and current_key:
            self.mistral_key = str(current_key)
        elif self.live:
            self._skip(
                "Live AI tests",
                "no Mistral API key in Odoo and none passed via --mistral-key",
            )
            self.live = False

    def _run_missing_key_test(self) -> None:
        print("\n--- Missing API key guard ---")

        if not self._cleanup_agent_ids:
            agent_id = self._create_mistral_agent("RPC Missing Key Agent")
        else:
            agent_id = self._cleanup_agent_ids[-1]

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

    def _run_live_context_tests(self) -> None:
        if not self.live:
            return

        print("\n--- Live context injection (ai.agent.get_direct_response) ---")

        agent_id = self._create_mistral_agent("RPC Context Mistral Agent")
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
            self._ok(
                "TC-CTX-01 response references secret context token",
                CTX_SECRET_TOKEN.lower() in text or "8842" in text,
                "",
            )

            control_prompt = f"What is the secret token {CTX_SECRET_TOKEN}? Reply with the token only."
            control = self.client.execute_kw(
                MODEL_AI_AGENT,
                "get_direct_response",
                [[agent_id], control_prompt, ""],
            )
            control_text = self._response_text(control)
            self._ok(
                "TC-CTX-02 without context does not reliably know injected secret",
                CTX_SECRET_TOKEN not in control_text,
                control_text[:120],
            )
        except RuntimeError as exc:
            self._ok("Live context injection via get_direct_response", False, str(exc)[:200])

    def _run_live_rag_tests(self) -> None:
        if not self.live:
            return

        print("\n--- Live RAG source context ---")

        agent_id = self._create_mistral_agent("RPC RAG Mistral Agent")
        rag_body = (
            f"Internal QA document.\n"
            f"The vault access code is {RAG_SECRET_CODE}.\n"
            f"Authorized personnel only.\n"
        ).encode("utf-8")
        files = [
            {
                "name": "rpc_rag_secret.txt",
                "datas": base64.b64encode(rag_body).decode("ascii"),
                "mimetype": "text/plain",
            }
        ]

        try:
            source_ids = self.client.execute_kw(
                MODEL_AI_AGENT_SOURCE,
                "create_from_binary_files",
                [files, agent_id],
            )
            if not source_ids:
                self._ok("TC-RAG-01 create_from_binary_files returns source", False)
                return

            source_id = source_ids[0] if isinstance(source_ids, list) else source_ids
            self._ok(
                "TC-RAG-01 RAG source created from binary file",
                bool(source_id),
                f"source_id={source_id}",
            )

            indexed = self._wait_for_source_indexed(source_id)
            self._ok(
                "TC-RAG-02 source indexed with Mistral embeddings",
                indexed,
                f"timeout={self.rag_timeout}s",
            )
            if not indexed:
                return

            response = self.client.execute_kw(
                MODEL_AI_AGENT,
                "get_direct_response",
                [[agent_id], "What is the vault access code? Reply with the code only.", ""],
            )
            text = self._response_text(response)
            self._ok(
                "TC-RAG-03 answer uses RAG document context",
                RAG_SECRET_CODE in text,
                text[:160],
            )
        except RuntimeError as exc:
            self._ok("Live RAG automation", False, str(exc)[:200])

    def _run_live_record_context_tests(self) -> None:
        if not self.live:
            return

        print("\n--- Live record ORM context (res.partner) ---")

        partner_name = "RPC Mistral Context Partner"
        partner_city = "Lyon"
        partner_id = self.client.create(
            MODEL_RES_PARTNER,
            {"name": partner_name, "city": partner_city},
        )
        try:
            context_message = (
                f"Record context: partner name is {partner_name}, city is {partner_city}. "
                "Answer using only this context."
            )
            prompt = "In which city is this partner located? Reply with the city name only."
            agent_id = self._create_mistral_agent("RPC Record Context Agent")
            response = self.client.execute_kw(
                MODEL_AI_AGENT,
                "get_direct_response",
                [[agent_id], prompt, context_message],
            )
            text = self._response_text(response).lower()
            self._ok(
                "TC-CTX-03 record-style context surfaces partner city",
                partner_city.lower() in text,
                self._response_text(response)[:120],
            )
        except RuntimeError as exc:
            self._ok("Live record context scenario", False, str(exc)[:200])
        finally:
            try:
                self.client.unlink(MODEL_RES_PARTNER, [partner_id])
            except RuntimeError as exc:
                print(f"  [WARN] cleanup res.partner {partner_id}: {exc}")

    def _run_http_transcription_tests(self) -> None:
        if not self.live or not self.http:
            if self.live and not self.http:
                self._skip("HTTP transcription tests", "HTTP session client not initialized")
            return

        print("\n--- HTTP transcription controller (authenticated session) ---")

        try:
            session_result = self.http.call_controller_jsonrpc(
                ROUTE_TRANSCRIPTION_SESSION,
                {"language": "en"},
            )
            self._ok(
                "TC-HTTP-01 /ai/transcription/session responds",
                isinstance(session_result, dict),
                str(session_result)[:120],
            )
            if isinstance(session_result, dict):
                for key in ("session_id", "value", "expires_at", "session"):
                    self._ok(
                        f"TC-HTTP-01 session payload contains {key!r}",
                        key in session_result,
                    )

            # Empty payload should be rejected by the controller.
            status, empty_body = self.http.post_binary(
                ROUTE_TRANSCRIPTION_AUDIO,
                b"",
                "audio/webm",
            )
            self._ok(
                "TC-HTTP-02 empty audio rejected",
                status == 400,
                f"status={status} body={empty_body!r}"[:120],
            )
        except RuntimeError as exc:
            self._ok("HTTP transcription endpoints", False, str(exc)[:200])

    def run(self) -> bool:
        has_custom = self.custom.has_direct() or self.custom.has_rag()
        mode = "SMOKE (no external API calls)"
        if self.custom.custom_only and has_custom:
            mode = "CUSTOM (user prompt/context/RAG)"
        elif self.live:
            mode = "LIVE (Mistral API)"
        if has_custom and not self.custom.custom_only:
            mode += " + built-in suite"

        print("=" * 80)
        print("Mistral AI Connector — RPC / HTTP Test (Odoo 19)")
        print(f"Module : {MODULE_NAME}")
        print(
            f"Protocol: {self.client.protocol.upper()} | DB: {self.client.db} | URL: {self.client.url}"
        )
        print(f"Mode   : {mode}")
        print("=" * 80)

        try:
            self._ensure_live_ready()
            run_builtin = not self.custom.custom_only

            if run_builtin:
                self._run_structural_tests()
                self._run_config_tests()
                self._run_missing_key_test()

            if has_custom:
                if self.custom.has_rag():
                    self._run_custom_rag_test()
                else:
                    self._run_custom_direct_test()

            if run_builtin and self.live:
                self._run_live_context_tests()
                self._run_live_rag_tests()
                self._run_live_record_context_tests()
                self._run_http_transcription_tests()
        finally:
            self._restore_mistral_key()
            self._cleanup()

        print("=" * 80)
        print(f"Result: {self.passed} passed, {self.failed} failed, {self.skipped} skipped")
        print("=" * 80)
        return self.failed == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RPC / HTTP automation test for connect_mistral_ai (Odoo 19)",
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
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run live Mistral AI scenarios (context, RAG, HTTP). Requires API key.",
    )
    parser.add_argument(
        "--mistral-key",
        default=None,
        help="Mistral API key to store in connect_mistral_ai.mistral_key before live tests",
    )
    parser.add_argument(
        "--rag-timeout",
        type=int,
        default=180,
        help="Seconds to wait for RAG source indexing (default: 180)",
    )
    custom = parser.add_argument_group("custom scenario (optional)")
    custom.add_argument(
        "--prompt",
        help="Your question sent to ai.agent.get_direct_response",
    )
    custom.add_argument(
        "--context",
        help="Extra system context passed as context_message to get_direct_response",
    )
    custom.add_argument(
        "--context-file",
        help="Read context text from a file (used instead of --context)",
    )
    custom.add_argument(
        "--expect",
        action="append",
        default=[],
        help="Substring that must appear in the AI response (repeatable)",
    )
    custom.add_argument(
        "--rag-text",
        help="Custom document text indexed as RAG source before --prompt",
    )
    custom.add_argument(
        "--rag-file",
        help="Custom document file indexed as RAG source before --prompt",
    )
    custom.add_argument(
        "--agent-id",
        type=int,
        default=None,
        help="Use an existing ai.agent (not deleted on cleanup)",
    )
    custom.add_argument(
        "--llm-model",
        default=DEFAULT_LIVE_LLM,
        help=f"Mistral model when creating a temporary agent (default: {DEFAULT_LIVE_LLM})",
    )
    custom.add_argument(
        "--custom-only",
        action="store_true",
        help="Run only your --prompt/--context/--rag-* scenario (skip built-in tests)",
    )
    custom.add_argument(
        "--print-response",
        action="store_true",
        help="Print the full AI response to stdout",
    )
    return parser.parse_args()


def _build_custom_scenario(args: argparse.Namespace) -> CustomScenario:
    return CustomScenario(
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


def _validate_custom_args(custom: CustomScenario) -> None:
    if custom.context and custom.context_file:
        raise SystemExit("ERROR: use either --context or --context-file, not both")
    if custom.rag_text and custom.rag_file:
        raise SystemExit("ERROR: use either --rag-text or --rag-file, not both")
    if custom.context_file and not Path(custom.context_file).is_file():
        raise SystemExit(f"ERROR: context file not found: {custom.context_file}")
    if custom.rag_file and not Path(custom.rag_file).is_file():
        raise SystemExit(f"ERROR: RAG file not found: {custom.rag_file}")

    needs_prompt = bool(
        custom.context
        or custom.context_file
        or custom.rag_text
        or custom.rag_file
        or custom.expect
        or custom.custom_only
    )
    if needs_prompt and not custom.prompt:
        raise SystemExit(
            "ERROR: --prompt is required with --context, --rag-*, --expect, or --custom-only"
        )
    if custom.custom_only and not (custom.has_direct() or custom.has_rag()):
        raise SystemExit(
            "ERROR: --custom-only requires --prompt (and optional --context / --rag-*)"
        )


def main() -> int:
    args = parse_args()
    custom = _build_custom_scenario(args)
    try:
        _validate_custom_args(custom)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 1

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
            print(f"WARN: HTTP session auth failed, skipping controller tests: {exc}", file=sys.stderr)

    success = ConnectMistralAIRPCTest(
        client,
        live=live,
        mistral_key=args.mistral_key,
        rag_timeout=args.rag_timeout,
        http_client=http_client,
        custom=custom,
    ).run()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
