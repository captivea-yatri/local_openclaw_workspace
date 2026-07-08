"""Odoo JSON-RPC / XML-RPC client for cap_qa_platform."""
from __future__ import annotations

import json
import xmlrpc.client
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cap_qa_platform.rpc.errors import RpcError


def sanitize_for_rpc(value: Any) -> Any:
    if value is None:
        return False
    if isinstance(value, dict):
        return {k: sanitize_for_rpc(v) for k, v in value.items() if v is not None}
    if isinstance(value, (list, tuple)):
        return [sanitize_for_rpc(item) for item in value]
    return value


def m2o_id(value: Any) -> int | None:
    if not value:
        return None
    if isinstance(value, (list, tuple)):
        return value[0]
    return value


class OdooRPCClient:
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
            raise RpcError(f"Authentication failed for {username!r}")
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
            raise RpcError(f"HTTP error {exc.code}: {exc.reason}") from exc
        except URLError as exc:
            raise RpcError(f"Cannot reach Odoo at {self.url}: {exc}") from exc
        if body.get("error"):
            err = body["error"]
            msg = err.get("data", {}).get("message") or err.get("message") or str(err)
            raise RpcError(msg)
        return body.get("result")

    def execute_kw(
        self,
        model: str,
        method: str,
        args: list | None = None,
        kwargs: dict | None = None,
    ) -> Any:
        if self.uid is None:
            raise RpcError("Not authenticated")
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
            "object",
            "execute_kw",
            [self.db, self.uid, self.password, model, method, args, kwargs],
        )

    def call(self, model: str, method: str, *args, **kwargs) -> Any:
        context = kwargs.pop("context", None)
        clean_args = [sanitize_for_rpc(arg) for arg in args]
        clean_kwargs = sanitize_for_rpc(kwargs) if kwargs else {}
        if context:
            clean_kwargs["context"] = context
        return self.execute_kw(model, method, clean_args, clean_kwargs)

    def search(
        self, model: str, domain: list, limit: int | None = None, order: str | None = None
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
        fields: list[str] | None = None,
        limit: int | None = None,
        order: str | None = None,
    ) -> list[dict]:
        kwargs: dict[str, Any] = {}
        if fields:
            kwargs["fields"] = fields
        if limit is not None:
            kwargs["limit"] = limit
        if order:
            kwargs["order"] = order
        return self.execute_kw(model, "search_read", [domain], kwargs)

    def search_count(self, model: str, domain: list) -> int:
        return self.execute_kw(model, "search_count", [domain])

    def read(self, model: str, ids: list[int], fields: list[str]) -> list[dict]:
        if not ids:
            return []
        return self.execute_kw(model, "read", [ids, fields])

    def create(self, model: str, vals: dict, context: dict | None = None) -> int:
        kwargs = {"context": context} if context else {}
        return self.execute_kw(model, "create", [sanitize_for_rpc(vals)], kwargs)

    def copy(
        self,
        model: str,
        record_id: int,
        default: dict | None = None,
        context: dict | None = None,
    ) -> int:
        kwargs: dict[str, Any] = {}
        if context:
            kwargs["context"] = context
        args: list[Any] = [record_id]
        if default:
            args.append(sanitize_for_rpc(default))
        return self.execute_kw(model, "copy", args, kwargs)

    def write(
        self, model: str, ids: list[int], vals: dict, context: dict | None = None
    ) -> bool:
        kwargs = {"context": context} if context else {}
        return self.execute_kw(model, "write", [ids, sanitize_for_rpc(vals)], kwargs)

    def unlink(self, model: str, ids: list[int]) -> bool:
        return self.execute_kw(model, "unlink", [ids])

    def fields_get(self, model: str, attributes: list[str] | None = None) -> dict:
        kwargs: dict[str, Any] = {}
        if attributes:
            kwargs["attributes"] = attributes
        return self.execute_kw(model, "fields_get", [], kwargs)
