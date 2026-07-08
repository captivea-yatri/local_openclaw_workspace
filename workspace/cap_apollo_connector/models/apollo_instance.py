# -*- coding: utf-8 -*-
import json
import logging
from urllib.parse import urlparse

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..const import APOLLO_API_BASE_URL, APOLLO_API_KEY_HEADER, APOLLO_REQUEST_TIMEOUT

_logger = logging.getLogger(__name__)


class ApolloInstance(models.Model):
    _name = "apollo.instance"
    _description = "Apollo.io connection"
    _order = "name, id"

    def _get_company_domain(self):
        return [("id", "in", self.env.context.get("allowed_company_ids") or [])]

    name = fields.Char(required=True, string="Instance Name")
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        domain=_get_company_domain,
    )
    active = fields.Boolean(default=True)
    api_base_url = fields.Char(
        string="API Base URL",
        required=True,
        default=APOLLO_API_BASE_URL,
        help="Apollo REST API base URL. Default: https://api.apollo.io/api/v1",
    )
    api_key = fields.Char(
        string="API Key",
        required=True,
        help="Create an API key in Apollo: Settings > Integrations > Apollo API > API Keys.",
    )
    is_master_key = fields.Boolean(
        string="Master API Key",
        help="Some Apollo endpoints require a master key. Enable this if you created "
        "the key with 'Set as master key' in Apollo.",
    )
    enrichment_webhook_url = fields.Char(
        string="Enrichment Webhook URL",
        help="Required HTTPS webhook when using phone number reveal in People Enrichment. "
        "Apollo sends phone numbers asynchronously to this URL.",
    )
    last_connection_test = fields.Datetime(string="Last Connection Test", readonly=True)
    connection_status = fields.Selection(
        [
            ("unknown", "Not tested"),
            ("connected", "Connected"),
            ("failed", "Failed"),
        ],
        string="Connection Status",
        default="unknown",
        readonly=True,
    )
    connection_message = fields.Char(string="Connection Message", readonly=True)

    @api.constrains("api_base_url")
    def _check_api_base_url(self):
        for rec in self:
            url = (rec.api_base_url or "").strip()
            if not url.startswith("https://"):
                raise ValidationError(_("Apollo API base URL must start with https://."))

    @api.constrains("enrichment_webhook_url")
    def _check_enrichment_webhook_url(self):
        for rec in self:
            url = (rec.enrichment_webhook_url or "").strip()
            if url and not url.startswith("https://"):
                raise ValidationError(_("Enrichment webhook URL must start with https://."))

    @api.constrains("company_id")
    def _check_single_active_instance_per_company(self):
        for rec in self.filtered("active"):
            duplicate = self.search(
                [
                    ("id", "!=", rec.id),
                    ("company_id", "=", rec.company_id.id),
                    ("active", "=", True),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    _(
                        "Company %(company)s already has an active Apollo instance "
                        "(%(instance)s). Deactivate it before creating another one."
                    )
                    % {"company": rec.company_id.display_name, "instance": duplicate.name}
                )

    def _get_api_key(self):
        self.ensure_one()
        api_key = (self.api_key or "").strip()
        if not api_key:
            raise UserError(_("Set an Apollo API key before calling the API."))
        return api_key

    def _build_url(self, path):
        self.ensure_one()
        base = (self.api_base_url or APOLLO_API_BASE_URL).rstrip("/")
        if not path.startswith("/"):
            path = "/" + path
        return base + path

    def _build_headers(self, extra_headers=None):
        self.ensure_one()
        headers = {
            APOLLO_API_KEY_HEADER: self._get_api_key(),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Cache-Control": "no-cache",
        }
        if extra_headers:
            headers.update(extra_headers)
        return headers

    @staticmethod
    def _encode_apollo_query_params(payload):
        """Apollo enrichment endpoints expect filters as URL query parameters."""
        params = []
        for key, value in (payload or {}).items():
            if value is None or value == "":
                continue
            if isinstance(value, bool):
                params.append((key, "true" if value else "false"))
                continue
            params.append((key, value))
        return params

    def apollo_api_request(self, method, path, json_body=None, params=None, timeout=None):
        """Call the Apollo REST API with x-api-key authentication."""
        self.ensure_one()
        url = self._build_url(path)
        kwargs = {
            "method": method.upper(),
            "url": url,
            "headers": self._build_headers(),
            "timeout": timeout or APOLLO_REQUEST_TIMEOUT,
        }
        if params:
            kwargs["params"] = params
        if json_body is not None:
            kwargs["json"] = json_body

        _logger.info("Apollo %s %s", method.upper(), url)
        response = requests.request(**kwargs)
        try:
            body = response.json() if response.content else {}
        except Exception:
            body = {}

        if response.status_code >= 400:
            message = self._format_api_error(response.status_code, body)
            raise UserError(message)

        return body

    @staticmethod
    def _format_api_error(status_code, body):
        if isinstance(body, dict):
            for key in ("error", "message", "error_message"):
                if body.get(key):
                    detail = body[key]
                    break
            else:
                detail = json.dumps(body)
        else:
            detail = str(body)

        hints = {
            401: _(
                "Invalid or missing API key. Verify the key in Apollo "
                "(Settings > Integrations > Apollo API)."
            ),
            403: _(
                "Access denied. This endpoint may require a master API key."
            ),
            429: _("Rate limit exceeded. Wait and try again."),
        }
        hint = hints.get(status_code, "")
        msg = _("Apollo API error (%(status)s): %(detail)s") % {
            "status": status_code,
            "detail": detail[:2000],
        }
        if hint:
            msg = "%s\n\n%s" % (msg, hint)
        return msg

    def enrich_person(self, params):
        """Enrich one person via Apollo People Enrichment (POST /people/match).

        See https://docs.apollo.io/reference/people-enrichment
        """
        self.ensure_one()
        if not isinstance(params, dict):
            raise UserError(_("Enrichment parameters must be a dictionary."))

        payload = dict(params)
        if payload.get("reveal_phone_number"):
            webhook_url = (payload.get("webhook_url") or self.enrichment_webhook_url or "").strip()
            if not webhook_url:
                raise UserError(
                    _(
                        "Phone reveal requires an HTTPS webhook URL. Set it on the Apollo "
                        "instance (Enrichment Webhook URL) or pass webhook_url in the request."
                    )
                )
            payload["webhook_url"] = webhook_url

        query_params = self._encode_apollo_query_params(payload)
        _logger.info("Apollo people enrichment params: %s", query_params)
        return self.apollo_api_request("POST", "/people/match", params=query_params)

    def search_contacts(self, params):
        """Search contacts via Apollo API (GET /contacts/search).

        ``params`` is a dict of query filters – they are encoded into URL parameters.
        """
        self.ensure_one()
        if not isinstance(params, dict):
            raise UserError(_("Search parameters must be a dictionary."))
        query_params = self._encode_apollo_query_params(params)
        _logger.info("Apollo contacts search params: %s", query_params)
        return self.apollo_api_request("GET", "/contacts/search", params=query_params)

    def action_test_connection(self):
        self.ensure_one()
        try:
            payload = self.apollo_api_request("GET", "/auth/health")
        except UserError as err:
            self.write(
                {
                    "last_connection_test": fields.Datetime.now(),
                    "connection_status": "failed",
                    "connection_message": str(err)[:255],
                }
            )
            raise

        is_logged_in = bool(payload.get("is_logged_in"))
        healthy = bool(payload.get("healthy", True))
        if not healthy or not is_logged_in:
            message = _(
                "Apollo responded but the API key is not valid. "
                "Create or regenerate the key in Apollo and update this instance."
            )
            self.write(
                {
                    "last_connection_test": fields.Datetime.now(),
                    "connection_status": "failed",
                    "connection_message": message,
                }
            )
            raise UserError(message)

        success_message = _("Apollo connection successful.")
        if self.is_master_key:
            success_message = _("Apollo connection successful (master key validated).")

        self.write(
            {
                "last_connection_test": fields.Datetime.now(),
                "connection_status": "connected",
                "connection_message": success_message,
            }
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": success_message,
                "type": "success",
                "sticky": False,
            },
        }

    def action_open_people_enrichment(self):
        self.ensure_one()
        return {
            "name": _("People Enrichment"),
            "type": "ir.actions.act_window",
            "res_model": "apollo.people.enrichment",
            "view_mode": "form",
            "target": "new",
            "context": {"default_instance_id": self.id},
        }

    @api.model
    def get_company_instance(self, company=None):
        """Return the active Apollo instance for a company."""
        company = company or self.env.company
        return self.search(
            [("company_id", "=", company.id), ("active", "=", True)],
            limit=1,
        )
