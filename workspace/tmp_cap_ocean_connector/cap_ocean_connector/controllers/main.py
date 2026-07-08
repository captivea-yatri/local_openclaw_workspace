# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

from ..const import OCEAN_WEBHOOK_PATH

_logger = logging.getLogger(__name__)


class OceanWebhookController(http.Controller):
    def _log_webhook_attempt(
        self,
        route_id,
        instance=None,
        payload=None,
        payload_type="unknown",
        state="error",
        message="",
        http_status=200,
    ):
        Log = request.env["ocean.webhook.log"].sudo()
        return Log.create(
            {
                "instance_id": instance.id if instance else False,
                "webhook_token": route_id,
                "payload_type": payload_type,
                "state": state,
                "message": message[:255] if message else False,
                "payload_json": json.dumps(payload or {}, indent=2)[:500000]
                if payload is not None
                else False,
                "http_status": http_status,
            }
        )

    def _resolve_webhook_instance(self, path_token=None):
        """Resolve ocean.instance from ?secret= (doc format) or legacy path token."""
        Instance = request.env["ocean.instance"].sudo()
        secret = (request.httprequest.args.get("secret") or "").strip()
        if secret:
            instance = Instance.search(
                [("webhook_secret", "=", secret), ("active", "=", True)],
                limit=1,
            )
            if instance:
                return instance, secret
        if path_token:
            instance = Instance.search(
                [("webhook_token", "=", path_token), ("active", "=", True)],
                limit=1,
            )
            if instance:
                if instance.webhook_secret:
                    if secret != instance.webhook_secret:
                        return None, path_token
                return instance, path_token
        return None, secret or path_token or ""

    def _validate_webhook_secret(self, instance, route_id):
        secret = (request.httprequest.args.get("secret") or "").strip()
        expected = (instance.webhook_secret or "").strip()
        if expected and secret != expected:
            _logger.warning(
                "Ocean.io webhook rejected: invalid secret for instance %s", instance.id
            )
            self._log_webhook_attempt(
                route_id,
                instance=instance,
                message="Rejected: invalid ?secret= query parameter.",
                payload_type="unknown",
                state="error",
                http_status=403,
            )
            return False
        return True

    def _handle_ocean_webhook(self, path_token=None):
        """Shared handler for Ocean.io async webhook POST/GET (return 2xx per docs)."""
        instance, route_id = self._resolve_webhook_instance(path_token=path_token)

        if request.httprequest.method == "GET":
            if not instance:
                self._log_webhook_attempt(
                    route_id,
                    message="GET ping failed: unknown webhook secret or token.",
                    payload_type="ping",
                    state="error",
                    http_status=404,
                )
                return request.make_response("Not Found", status=404)
            if not self._validate_webhook_secret(instance, route_id):
                return request.make_response("Forbidden", status=403)
            self._log_webhook_attempt(
                route_id,
                instance=instance,
                payload={"ping": "ok"},
                payload_type="ping",
                state="processed",
                message="GET ping successful — Odoo webhook endpoint is reachable.",
                http_status=200,
            )
            return request.make_response("OK", status=200)

        if not instance:
            _logger.warning("Ocean.io webhook received for unknown route id: %s", route_id)
            self._log_webhook_attempt(
                route_id,
                message="POST rejected: unknown webhook secret or token.",
                payload_type="unknown",
                state="error",
                http_status=404,
            )
            return request.make_response("Not Found", status=404)

        if not self._validate_webhook_secret(instance, route_id):
            return request.make_response("Forbidden", status=403)

        raw_body = request.httprequest.get_data(as_text=True) or "{}"
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            _logger.warning("Ocean.io webhook received invalid JSON for instance %s", instance.id)
            self._log_webhook_attempt(
                route_id,
                instance=instance,
                payload={"raw_body": raw_body[:2000]},
                message="POST rejected: invalid JSON payload.",
                payload_type="unknown",
                state="error",
                http_status=400,
            )
            return request.make_response("Bad Request", status=400)

        try:
            log = instance.process_webhook_payload(payload)
        except Exception:
            _logger.exception(
                "Ocean.io webhook processing failed for instance %s (db=%s)",
                instance.id,
                request.db,
            )
            return request.make_response("Internal Server Error", status=500)

        _logger.info(
            "Ocean.io webhook OK for instance %s (db=%s, type=%s, updated=%s)",
            instance.id,
            request.db,
            log.payload_type,
            log.records_updated,
        )
        return request.make_response("OK", status=200)

    @http.route(
        OCEAN_WEBHOOK_PATH,
        type="http",
        auth="public",
        methods=["GET", "POST"],
        csrf=False,
    )
    def ocean_webhook_doc_path(self, **kwargs):
        """Primary receiver — matches Ocean.io docs: /webhooks/ocean?secret=..."""
        return self._handle_ocean_webhook()

    @http.route(
        "/ocean/webhook/<string:token>",
        type="http",
        auth="public",
        methods=["GET", "POST"],
        csrf=False,
    )
    def ocean_webhook_legacy(self, token, **kwargs):
        """Legacy path for instances created before /webhooks/ocean format."""
        return self._handle_ocean_webhook(path_token=token)
