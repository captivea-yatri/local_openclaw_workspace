# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime

from odoo import http
from odoo.http import request

from ..const import LUSHA_WEBHOOK_PATH

_logger = logging.getLogger(__name__)


class LushaWebhookController(http.Controller):
    def _resolve_webhook_instance(self):
        Instance = request.env["lusha.instance"].sudo()
        secret = (request.httprequest.args.get("secret") or "").strip()
        if not secret:
            return None
        return Instance.search(
            [("webhook_secret", "=", secret), ("active", "=", True)],
            limit=1,
        )

    def _log_attempt(self, instance=None, payload=None, state="error", message="", http_status=200):
        Log = request.env["lusha.webhook.log"].sudo()
        return Log.create(
            {
                "instance_id": instance.id if instance else False,
                "payload_type": (payload or {}).get("type") or "ping",
                "entity_type": (payload or {}).get("entityType") or "unknown",
                "state": state,
                "message": message[:255] if message else False,
                "payload_json": json.dumps(payload or {}, indent=2)[:500000]
                if payload is not None
                else False,
                "http_status": http_status,
            }
        )

    def _ack_response(self, payload, status=201):
        """Return Lusha-required acknowledgment JSON."""
        body = {
            "received": True,
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "webhookId": payload.get("id") if isinstance(payload, dict) else None,
        }
        return request.make_json_response(body, status=status)

    @http.route(
        LUSHA_WEBHOOK_PATH,
        type="http",
        auth="public",
        methods=["GET", "POST"],
        csrf=False,
    )
    def lusha_webhook(self, **kwargs):
        instance = self._resolve_webhook_instance()

        if request.httprequest.method == "GET":
            if not instance:
                self._log_attempt(message="GET ping failed: unknown secret.", http_status=404)
                return request.make_response("Not Found", status=404)
            self._log_attempt(
                instance=instance,
                payload={"ping": "ok"},
                state="processed",
                message="GET ping successful.",
                http_status=200,
            )
            return request.make_response("OK", status=200)

        if not instance:
            _logger.warning("Lusha webhook received for unknown secret.")
            self._log_attempt(message="POST rejected: unknown secret.", http_status=404)
            return request.make_response("Not Found", status=404)

        raw_body = request.httprequest.get_data(as_text=True) or "{}"
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            self._log_attempt(
                instance=instance,
                payload={"raw_body": raw_body[:2000]},
                message="POST rejected: invalid JSON.",
                http_status=400,
            )
            return request.make_response("Bad Request", status=400)

        headers = {k: v for k, v in request.httprequest.headers.items()}
        try:
            log = instance.process_webhook_payload(payload, headers=headers)
        except Exception:
            _logger.exception("Lusha webhook processing failed for instance %s", instance.id)
            return request.make_response("Internal Server Error", status=500)

        if log.state == "error" and log.message and "signature" in (log.message or "").lower():
            return request.make_response("Unauthorized", status=401)

        return self._ack_response(payload, status=201)
