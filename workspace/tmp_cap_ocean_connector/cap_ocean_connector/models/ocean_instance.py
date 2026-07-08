# -*- coding: utf-8 -*-
import json
import logging
import uuid
from urllib.parse import urlencode

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..const import (
    OCEAN_API_BASE_URL,
    OCEAN_API_TOKEN_HEADER,
    OCEAN_REQUEST_TIMEOUT,
    OCEAN_WEBHOOK_LEGACY_PATH_PREFIX,
    OCEAN_WEBHOOK_PATH,
)

_logger = logging.getLogger(__name__)


class OceanInstance(models.Model):
    _name = "ocean.instance"
    _description = "Ocean.io connection"
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
        default=OCEAN_API_BASE_URL,
        help="Ocean.io REST API base URL. Default: https://api.ocean.io",
    )
    api_token = fields.Char(
        string="API Token",
        required=True,
        help="Generate a token in Ocean.io: Account Settings → API Tokens.",
    )
    public_base_url = fields.Char(
        string="Public HTTPS URL (optional)",
        help="Public HTTPS address where Ocean.io can reach Odoo. "
        "Leave empty when System Parameters → web.base.url is already HTTPS (production). "
        "For local dev with ngrok, paste your ngrok URL (e.g. https://abc123.ngrok-free.app). "
        "The webhook URL below is built automatically on save.",
    )
    database = fields.Char(
        string="Odoo Database",
        readonly=True,
        help="Appended as ?db=... on the webhook URL so public requests reach this database.",
    )
    webhook_url = fields.Char(
        string="Webhook URL (auto)",
        compute="_compute_webhook_url",
        store=True,
        readonly=True,
        help="Auto-built HTTPS webhookUrl sent to Ocean.io (reveal emails/phones, batch enrich). "
        "Format: https://your-domain/webhooks/ocean?secret=...&db=...",
    )
    webhook_token = fields.Char(
        string="Webhook Token (legacy)",
        copy=False,
        readonly=True,
        default=lambda self: str(uuid.uuid4()),
        groups="base.group_no_one",
    )
    webhook_secret = fields.Char(
        string="Webhook Secret",
        copy=False,
        readonly=True,
        default=lambda self: str(uuid.uuid4()),
        help="Auto-generated secret token in the webhook URL (?secret=...) as recommended by "
        "Ocean.io. Do not paste your API token here.",
    )
    webhook_log_count = fields.Integer(compute="_compute_webhook_log_count")
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
    credit_recurrent = fields.Integer(string="Recurrent Credits", readonly=True)
    credit_one_time = fields.Integer(string="One-time Credits", readonly=True)
    email_credit_recurrent = fields.Integer(string="Email Credits", readonly=True)
    daily_rate_limit_left = fields.Integer(string="Daily Rate Limit Left", readonly=True)

    _sql_constraints = [
        (
            "webhook_secret_unique",
            "unique(webhook_secret)",
            "Each Ocean.io instance must have a unique webhook secret.",
        ),
    ]

    def _webhook_database_name(self):
        self.ensure_one()
        return (self.database or self.env.cr.dbname or "").strip()

    def _get_webhook_https_base(self):
        """Return the public HTTPS base URL for webhookUrl (Ocean.io requirement)."""
        self.ensure_one()
        icp = self.env["ir.config_parameter"].sudo()
        override = (self.public_base_url or "").strip().rstrip("/")
        base = override or icp.get_param("web.base.url", "").strip().rstrip("/")
        if not base.startswith("https://"):
            return False
        return base

    def _webhook_url_query_params(self):
        """Query string: ?secret=... (&db=... for Odoo database routing)."""
        self.ensure_one()
        secret = (self.webhook_secret or "").strip()
        if not secret:
            return {}
        params = {"secret": secret}
        dbname = self._webhook_database_name()
        if dbname:
            params["db"] = dbname
        return params

    def _build_webhook_url_value(self):
        """Build webhookUrl per https://app.ocean.io/docs/getting-started/webhooks"""
        self.ensure_one()
        base = self._get_webhook_https_base()
        params = self._webhook_url_query_params()
        if not base or not params.get("secret"):
            return False
        return "%s%s?%s" % (base, OCEAN_WEBHOOK_PATH, urlencode(params))

    @api.depends("public_base_url", "webhook_secret", "database")
    def _compute_webhook_url(self):
        for rec in self:
            rec.webhook_url = rec._build_webhook_url_value()

    @api.constrains("public_base_url")
    def _check_public_base_url(self):
        for rec in self:
            url = (rec.public_base_url or "").strip()
            if url and not url.startswith("https://"):
                raise ValidationError(
                    _("Public HTTPS URL must start with https:// (use ngrok HTTPS, not http://localhost).")
                )

    @api.constrains("webhook_url")
    def _check_webhook_url_https(self):
        for rec in self.filtered("webhook_url"):
            url = rec.webhook_url.strip()
            if not url.startswith("https://"):
                raise ValidationError(
                    _("Webhook URL must be publicly reachable over HTTPS (Ocean.io requirement).")
                )
            if OCEAN_WEBHOOK_PATH not in url:
                _logger.warning(
                    "Ocean.io instance %s webhook_url does not use standard path %s",
                    rec.id,
                    OCEAN_WEBHOOK_PATH,
                )
            if "secret=" not in url:
                raise ValidationError(
                    _("Webhook URL must include ?secret=... as documented by Ocean.io.")
                )

    def _compute_webhook_log_count(self):
        Log = self.env["ocean.webhook.log"]
        data = Log.read_group(
            [("instance_id", "in", self.ids)],
            ["instance_id"],
            ["instance_id"],
        )
        mapped = {item["instance_id"][0]: item["instance_id_count"] for item in data}
        for rec in self:
            rec.webhook_log_count = mapped.get(rec.id, 0)

    @api.model_create_multi
    def create(self, vals_list):
        icp = self.env["ir.config_parameter"].sudo()
        default_base = icp.get_param("web.base.url", "")
        dbname = self.env.cr.dbname
        for vals in vals_list:
            if not vals.get("webhook_token"):
                vals["webhook_token"] = str(uuid.uuid4())
            if not vals.get("webhook_secret"):
                vals["webhook_secret"] = str(uuid.uuid4())
            if not vals.get("database") and dbname:
                vals["database"] = dbname
            if not vals.get("public_base_url") and default_base.startswith("https://"):
                vals["public_base_url"] = default_base.rstrip("/")
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if "public_base_url" in vals and "database" not in vals:
            vals["database"] = self.env.cr.dbname
        result = super().write(vals)
        for rec in self.filtered(lambda r: not (r.webhook_secret or "").strip()):
            super(OceanInstance, rec).write({"webhook_secret": str(uuid.uuid4())})
        return result

    def _ensure_webhook_credentials(self):
        """Backfill legacy instances and recompute webhookUrl."""
        for rec in self:
            updates = {}
            if not rec.webhook_token:
                updates["webhook_token"] = str(uuid.uuid4())
            if not (rec.webhook_secret or "").strip():
                updates["webhook_secret"] = str(uuid.uuid4())
            if not rec.database:
                updates["database"] = rec.env.cr.dbname
            if updates:
                rec.write(updates)

    def _webhook_request_headers(self):
        return {
            "Content-Type": "application/json",
            "ngrok-skip-browser-warning": "1",
            "User-Agent": "Odoo-Ocean-Webhook-Test/1.0",
        }

    @staticmethod
    def _webhook_response_is_ngrok_error(status_code, body):
        body = body or ""
        return status_code == 404 and "ngrok" in body.lower() and "<!doctype html" in body.lower()

    def action_refresh_webhook_url(self):
        """Rebuild webhookUrl from current HTTPS base + secret (Ocean.io format)."""
        self.ensure_one()
        self._ensure_webhook_credentials()
        if not self._get_webhook_https_base():
            raise UserError(
                _(
                    "Cannot build a webhook URL: Odoo needs a public HTTPS address.\n\n"
                    "Production: set System Parameters → web.base.url to https://your-domain\n"
                    "Local dev: run ngrok http 8069 and paste the HTTPS URL in Public HTTPS URL, "
                    "then save."
                )
            )
        if not (self.webhook_url or "").strip():
            raise UserError(_("Could not build webhook URL. Save the form and try again."))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Webhook URL ready"),
                "message": self.webhook_url,
                "type": "success",
                "sticky": True,
            },
        }

    def action_test_webhook_remote(self):
        """GET the auto-built webhookUrl to verify public HTTPS reachability."""
        self.ensure_one()
        self._ensure_webhook_credentials()
        if not self._get_webhook_https_base():
            raise UserError(
                _(
                    "Set a public HTTPS address first.\n\n"
                    "Local dev: ngrok http 8069 → paste HTTPS URL in Public HTTPS URL → Save.\n"
                    "Production: ensure web.base.url is https://your-domain."
                )
            )
        url = (self.webhook_url or "").strip()
        if OCEAN_WEBHOOK_PATH not in url or "secret=" not in url:
            raise UserError(
                _(
                    "Webhook URL was not built correctly. Upgrade the module, save this form, "
                    "and confirm the URL looks like:\n"
                    "https://your-domain/webhooks/ocean?secret=...&db=..."
                )
            )

        before_count = self.env["ocean.webhook.log"].sudo().search_count(
            [("instance_id", "=", self.id)]
        )
        headers = self._webhook_request_headers()
        try:
            response = requests.get(url, headers=headers, timeout=30)
        except requests.RequestException as err:
            raise UserError(
                _(
                    "Could not reach your webhook URL:\n%(url)s\n\nError: %(error)s\n\n"
                    "1. Start ngrok: ngrok http 8069\n"
                    "2. Copy the new https://....ngrok-free.app URL\n"
                    "3. Paste it in Public HTTPS URL and save"
                )
                % {"url": url, "error": err}
            ) from err

        body = response.text or ""
        if self._webhook_response_is_ngrok_error(response.status_code, body):
            raise UserError(
                _(
                    "ngrok returned HTTP 404 — the tunnel is offline or Public HTTPS URL "
                    "is outdated.\n\n"
                    "1. Run: ngrok http 8069\n"
                    "2. Copy the new HTTPS forwarding URL\n"
                    "3. Paste it in Public HTTPS URL and save\n"
                    "4. Run this test again\n\n"
                    "Current URL tested:\n%(url)s"
                )
                % {"url": url}
            )

        after_count = self.env["ocean.webhook.log"].sudo().search_count(
            [("instance_id", "=", self.id)]
        )
        reached_odoo = after_count > before_count
        log = self.env["ocean.webhook.log"].sudo().search(
            [("instance_id", "=", self.id)],
            order="id desc",
            limit=1,
        )

        if response.status_code >= 400:
            hint = ""
            if response.status_code == 404 and "db=" in url:
                hint = _(
                    "\n\nOdoo returned 404. Confirm the module is upgraded, Odoo is running "
                    "on the port ngrok forwards to (usually 8069), and the webhook token matches."
                )
            raise UserError(
                _(
                    "Webhook URL returned HTTP %(status)s.\n\nURL: %(url)s\n\n"
                    "Response: %(body)s%(hint)s"
                )
                % {
                    "status": response.status_code,
                    "url": url,
                    "body": body[:500],
                    "hint": hint,
                }
            )

        message = _(
            "HTTP %(status)s — Odoo webhook endpoint is reachable. %(detail)s"
        ) % {
            "status": response.status_code,
            "detail": log.message
            if reached_odoo and log
            else _(
                "The URL responded with HTTP 200 but no webhook log was created. "
                "Check that ?db= in the URL matches your Odoo database name."
            ),
        }
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Webhook connectivity OK"),
                "message": message,
                "type": "success" if reached_odoo else "warning",
                "sticky": True,
            },
        }

    def action_open_webhook_logs(self):
        self.ensure_one()
        return {
            "name": _("Ocean.io Webhook Logs"),
            "type": "ir.actions.act_window",
            "res_model": "ocean.webhook.log",
            "view_mode": "list,form",
            "domain": [("instance_id", "=", self.id)],
            "context": {"default_instance_id": self.id},
        }

    @api.constrains("webhook_url")
    def _check_webhook_url_points_to_odoo(self):
        for rec in self.filtered("webhook_url"):
            url = rec.webhook_url.strip()
            if OCEAN_WEBHOOK_PATH not in url and OCEAN_WEBHOOK_LEGACY_PATH_PREFIX not in url:
                _logger.warning(
                    "Ocean.io instance %s webhook_url may not point to Odoo webhook controller",
                    rec.id,
                )

    def register_webhook_targets(
        self,
        person_ids,
        partner_id=None,
        lead_id=None,
        target_types=None,
    ):
        """Link Ocean person IDs to Odoo records before async webhook arrives."""
        self.ensure_one()
        Target = self.env["ocean.webhook.target"].sudo()
        person_ids = [pid for pid in (person_ids or []) if pid]
        if not person_ids:
            return
        types = target_types or ["email"]
        for ocean_person_id in person_ids:
            for target_type in types:
                existing = Target.search(
                    [
                        ("instance_id", "=", self.id),
                        ("ocean_person_id", "=", ocean_person_id),
                        ("target_type", "=", target_type),
                    ],
                    limit=1,
                )
                vals = {
                    "instance_id": self.id,
                    "ocean_person_id": ocean_person_id,
                    "partner_id": partner_id,
                    "lead_id": lead_id,
                    "target_type": target_type,
                    "active": True,
                }
                if existing:
                    existing.write(vals)
                else:
                    Target.create(vals)

    @api.constrains("api_base_url")
    def _check_api_base_url(self):
        for rec in self:
            url = (rec.api_base_url or "").strip()
            if not url.startswith("https://"):
                raise ValidationError(_("Ocean.io API base URL must start with https://."))

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
                        "Company %(company)s already has an active Ocean.io instance "
                        "(%(instance)s). Deactivate it before creating another one."
                    )
                    % {"company": rec.company_id.display_name, "instance": duplicate.name}
                )

    def _get_api_token(self):
        self.ensure_one()
        api_token = (self.api_token or "").strip()
        if not api_token:
            raise UserError(_("Set an Ocean.io API token before calling the API."))
        return api_token

    def _build_url(self, path):
        self.ensure_one()
        base = (self.api_base_url or OCEAN_API_BASE_URL).rstrip("/")
        if not path.startswith("/"):
            path = "/" + path
        return base + path

    def _build_headers(self, extra_headers=None):
        self.ensure_one()
        headers = {
            OCEAN_API_TOKEN_HEADER: self._get_api_token(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def _get_webhook_url(self, override=None, purpose=None):
        self.ensure_one()
        webhook_url = (override or self.webhook_url or "").strip()
        if not webhook_url:
            if purpose:
                raise UserError(
                    _(
                        "%(purpose)s requires an HTTPS webhook URL on the Ocean.io instance.\n\n"
                        "Either set Webhook URL under Ocean.io → Configuration, or disable "
                        "the reveal/async option you enabled."
                    )
                    % {"purpose": purpose}
                )
            raise UserError(
                _(
                    "This Ocean.io endpoint requires an HTTPS webhook URL. "
                    "Set it on the Ocean.io instance (Webhook URL)."
                )
            )
        return webhook_url

    def ocean_api_request(self, method, path, json_body=None, params=None, timeout=None):
        """Call the Ocean.io REST API with X-Api-Token authentication."""
        self.ensure_one()
        url = self._build_url(path)
        kwargs = {
            "method": method.upper(),
            "url": url,
            "headers": self._build_headers(),
            "timeout": timeout or OCEAN_REQUEST_TIMEOUT,
        }
        if params:
            kwargs["params"] = params
        if json_body is not None:
            kwargs["json"] = json_body

        _logger.info("Ocean.io %s %s", method.upper(), url)
        try:
            response = requests.request(**kwargs)
        except requests.RequestException as err:
            _logger.warning("Ocean.io request failed for %s %s: %s", method.upper(), url, err)
            raise UserError(
                _(
                    "Could not reach Ocean.io at %(url)s.\n\n"
                    "Network error: %(error)s\n\n"
                    "Check your internet connection and that %(base)s is reachable from this server."
                )
                % {
                    "url": url,
                    "error": err,
                    "base": (self.api_base_url or OCEAN_API_BASE_URL).rstrip("/"),
                }
            ) from err

        raw_text = response.text or ""
        try:
            body = response.json() if response.content else {}
        except Exception:
            body = {}

        if response.status_code >= 400:
            message = self._format_api_error(response.status_code, body, raw_text)
            _logger.warning(
                "Ocean.io API error %s for %s %s: %s",
                response.status_code,
                method.upper(),
                url,
                raw_text[:1000],
            )
            raise UserError(message)

        return body

    @staticmethod
    def _format_api_error(status_code, body, raw_text=""):
        if isinstance(body, dict):
            detail = body.get("detail")
            if isinstance(detail, list):
                detail = "; ".join(str(item) for item in detail)
            elif detail is None:
                detail = False
                for key in ("error", "message", "error_message", "title"):
                    if body.get(key):
                        detail = body[key]
                        break
                if detail is False and body:
                    detail = json.dumps(body)
        else:
            detail = str(body)

        if not detail:
            stripped = (raw_text or "").strip()
            detail = stripped[:2000] if stripped else _("Empty response from Ocean.io")

        hints = {
            401: _("Invalid or missing API token."),
            402: _("Payment required. Check your Ocean.io credit balance and plan."),
            403: _(
                "Access denied. Paste your API token in the API Token field only "
                "(Account Settings → API Tokens in Ocean.io). Do not use the webhook secret field."
            ),
            404: _(
                "No unique high-confidence match. Add LinkedIn, email, or "
                "first name + last name + company domain + job title, "
                "or use People search mode."
            ),
            429: _("Rate limit exceeded. Wait and try again."),
            500: _(
                "Ocean.io returned a server error. This is on Ocean.io's side — "
                "Test Connection does not consume credits. Wait a few minutes and "
                "try again. If it persists, verify your API token in Ocean.io or "
                "contact Ocean.io support."
            ),
            502: _("Ocean.io or its gateway is temporarily unavailable. Retry shortly."),
            503: _("Ocean.io is temporarily unavailable. Retry shortly."),
            504: _("Ocean.io did not respond in time. Retry shortly."),
        }
        hint = hints.get(status_code, "")
        msg = _("Ocean.io API error (%(status)s): %(detail)s") % {
            "status": status_code,
            "detail": str(detail)[:2000],
        }
        if hint:
            msg = "%s\n\n%s" % (msg, hint)
        return msg

    def get_credits_balance(self):
        """GET /v2/credits/balance — verify authentication and read credits."""
        self.ensure_one()
        return self.ocean_api_request("GET", "/v2/credits/balance")

    def lookup_people(self, linkedin_handles=None, ocean_ids=None):
        """POST /v2/lookup/people — enrich people by LinkedIn handle or Ocean ID."""
        self.ensure_one()
        linkedin_handles = [h.strip() for h in (linkedin_handles or []) if h and h.strip()]
        ocean_ids = [oid.strip() for oid in (ocean_ids or []) if oid and oid.strip()]
        if not linkedin_handles and not ocean_ids:
            raise UserError(_("Provide at least one LinkedIn handle or Ocean person ID."))
        if len(linkedin_handles) + len(ocean_ids) > 1000:
            raise UserError(_("Lookup supports up to 1,000 identifiers per request."))

        payload = {}
        if linkedin_handles:
            payload["linkedinHandles"] = linkedin_handles
        if ocean_ids:
            payload["oceanIds"] = ocean_ids
        return self.ocean_api_request("POST", "/v2/lookup/people", json_body=payload)

    def enrich_person(
        self,
        person_data,
        company_data=None,
        reveal_emails=False,
        reveal_phones=False,
        webhook_url=None,
        partner_id=None,
        lead_id=None,
    ):
        """POST /v2/enrich/person — match and enrich a single person (sync)."""
        self.ensure_one()
        if not person_data:
            raise UserError(_("Provide person data for Ocean.io enrichment."))

        payload = {"person": dict(person_data)}
        if company_data:
            payload["company"] = dict(company_data)
        if reveal_emails:
            payload["revealEmails"] = {
                "includeEmails": True,
                "webhookUrl": self._get_webhook_url(
                    webhook_url,
                    purpose=_("Reveal Emails on People Lookup"),
                ),
            }
        if reveal_phones:
            payload["revealPhones"] = {
                "includePhones": True,
                "webhookUrl": self._get_webhook_url(
                    webhook_url,
                    purpose=_("Reveal Phones on People Lookup"),
                ),
            }
        response = self.ocean_api_request("POST", "/v2/enrich/person", json_body=payload)
        ocean_id = response.get("id") or person_data.get("id")
        if ocean_id and (reveal_emails or reveal_phones):
            types = []
            if reveal_emails:
                types.append("email")
            if reveal_phones:
                types.append("phone")
            self.register_webhook_targets(
                [ocean_id],
                partner_id=partner_id,
                lead_id=lead_id,
                target_types=types,
            )
        return response

    def search_people(self, payload=None):
        """POST /v3/search/people — search people with company and people filters."""
        self.ensure_one()
        return self.ocean_api_request("POST", "/v3/search/people", json_body=payload or {})

    def search_companies(self, payload=None):
        """POST /v3/search/companies — search companies with filters."""
        self.ensure_one()
        return self.ocean_api_request("POST", "/v3/search/companies", json_body=payload or {})

    def enrich_companies(self, company_data_mapping, webhook_url=None):
        """POST /v2/enrich/companies — batch enrich companies (async via webhook)."""
        self.ensure_one()
        if not company_data_mapping:
            raise UserError(_("Provide at least one company domain to enrich."))
        payload = {
            "companyDataMapping": company_data_mapping,
            "webhookUrl": self._get_webhook_url(
                webhook_url,
                purpose=_("Company Enrichment"),
            ),
        }
        return self.ocean_api_request("POST", "/v2/enrich/companies", json_body=payload)

    def reveal_emails(self, person_ids, webhook_url=None, partner_id=None, lead_id=None):
        """POST /v2/reveal/emails — reveal verified emails (async via webhook)."""
        self.ensure_one()
        person_ids = [pid.strip() for pid in (person_ids or []) if pid and pid.strip()]
        if not person_ids:
            raise UserError(_("Select at least one person to reveal emails for."))
        if len(person_ids) > 500:
            raise UserError(_("Email reveal supports up to 500 person IDs per request."))
        payload = {
            "personIds": person_ids,
            "webhookUrl": self._get_webhook_url(
                webhook_url,
                purpose=_("Reveal Emails"),
            ),
        }
        response = self.ocean_api_request("POST", "/v2/reveal/emails", json_body=payload)
        self.register_webhook_targets(
            person_ids,
            partner_id=partner_id,
            lead_id=lead_id,
            target_types=["email"],
        )
        return response

    def reveal_phones(self, person_ids, webhook_url=None, partner_id=None, lead_id=None):
        """POST /v2/reveal/phones — reveal phone numbers (async via webhook)."""
        self.ensure_one()
        person_ids = [pid.strip() for pid in (person_ids or []) if pid and pid.strip()]
        if not person_ids:
            raise UserError(_("Select at least one person to reveal phones for."))
        if len(person_ids) > 500:
            raise UserError(_("Phone reveal supports up to 500 person IDs per request."))
        payload = {
            "personIds": person_ids,
            "webhookUrl": self._get_webhook_url(
                webhook_url,
                purpose=_("Reveal Phones"),
            ),
        }
        response = self.ocean_api_request("POST", "/v2/reveal/phones", json_body=payload)
        self.register_webhook_targets(
            person_ids,
            partner_id=partner_id,
            lead_id=lead_id,
            target_types=["phone"],
        )
        return response

    def action_test_connection(self):
        self.ensure_one()
        token = (self.api_token or "").strip()
        if not token:
            raise UserError(
                _(
                    "Set your Ocean.io API token first (Account Settings → API Tokens in Ocean.io)."
                )
            )
        if token.startswith("http://") or token.startswith("https://"):
            raise UserError(
                _(
                    "The API Token field should contain your Ocean.io API key (starts with "
                    "api_...), not a URL. Paste the token from Ocean.io → Account Settings → "
                    "API Tokens."
                )
            )
        try:
            payload = self.get_credits_balance()
        except UserError as err:
            self.write(
                {
                    "last_connection_test": fields.Datetime.now(),
                    "connection_status": "failed",
                    "connection_message": str(err)[:255],
                }
            )
            raise

        credits = payload.get("credits") or {}
        email_credits = payload.get("emailCredits") or {}
        success_message = _("Ocean.io connection successful.")
        self.write(
            {
                "last_connection_test": fields.Datetime.now(),
                "connection_status": "connected",
                "connection_message": success_message,
                "credit_recurrent": credits.get("recurrent") or 0,
                "credit_one_time": credits.get("oneTime") or 0,
                "email_credit_recurrent": email_credits.get("recurrent") or 0,
                "daily_rate_limit_left": payload.get("dailyLimitRateLeft") or 0,
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
            "name": _("People Lookup"),
            "type": "ir.actions.act_window",
            "res_model": "ocean.people.enrichment",
            "view_mode": "form",
            "target": "new",
            "context": {"default_instance_id": self.id},
        }

    def action_open_lead_prospect(self):
        self.ensure_one()
        return {
            "name": _("Lead Prospecting"),
            "type": "ir.actions.act_window",
            "res_model": "ocean.lead.prospect",
            "view_mode": "form",
            "target": "new",
            "context": {"default_instance_id": self.id},
        }

    def action_open_company_enrichment(self):
        self.ensure_one()
        return {
            "name": _("Company Enrichment"),
            "type": "ir.actions.act_window",
            "res_model": "ocean.company.enrichment",
            "view_mode": "form",
            "target": "new",
            "context": {"default_instance_id": self.id},
        }

    @api.model
    def get_company_instance(self, company=None):
        """Return the active Ocean.io instance for a company."""
        company = company or self.env.company
        return self.search(
            [("company_id", "=", company.id), ("active", "=", True)],
            limit=1,
        )

    @staticmethod
    def extract_person_email(person):
        email = person.get("email")
        if isinstance(email, dict):
            return email.get("address")
        if isinstance(email, str):
            return email
        inferred = person.get("inferredEmails") or []
        return inferred[0] if inferred else False

    @staticmethod
    def extract_person_phone(person):
        phone = person.get("phone")
        if isinstance(phone, dict):
            numbers = phone.get("numbers") or []
            return numbers[0] if numbers else False
        if isinstance(phone, str):
            return phone
        return False

    @staticmethod
    def extract_person_email_status(person):
        email = person.get("email")
        if isinstance(email, dict):
            return email.get("status")
        return False

    @staticmethod
    def split_person_name(person):
        first_name = person.get("firstName") or ""
        last_name = person.get("lastName") or ""
        if first_name or last_name:
            return first_name, last_name
        full_name = (person.get("name") or "").strip()
        if not full_name:
            return "", ""
        parts = full_name.split(None, 1)
        return parts[0], parts[1] if len(parts) > 1 else ""

    @staticmethod
    def extract_company_name(person):
        company = person.get("company") or {}
        if isinstance(company, dict):
            return company.get("name") or company.get("companyName")
        return False

    @staticmethod
    def linkedin_handle_from_url(linkedin_url):
        linkedin_url = (linkedin_url or "").strip().rstrip("/")
        if not linkedin_url:
            return False
        if "/in/" in linkedin_url:
            return linkedin_url.split("/in/", 1)[1].split("/", 1)[0]
        return False

    @staticmethod
    def normalize_linkedin_for_enrich(linkedin_url=None, linkedin_handle=None):
        """Return linkedin.com/in/handle format expected by /v2/enrich/person."""
        handle = (linkedin_handle or "").strip().strip("/")
        if not handle and linkedin_url:
            handle = OceanInstance.linkedin_handle_from_url(linkedin_url)
        if not handle:
            return False
        if handle.startswith("linkedin.com/"):
            return handle
        if "linkedin.com/in/" in handle:
            return handle.split("://", 1)[-1]
        return "linkedin.com/in/%s" % handle

    @staticmethod
    def extract_reveal_email(item):
        """Extract email address from reveal / enrich_person_email webhook items."""
        if not isinstance(item, dict):
            return False, False, False
        ocean_person_id = item.get("personId") or item.get("id")
        email_data = item.get("email")
        address = False
        status = False
        if isinstance(email_data, dict):
            address = email_data.get("address")
            status = email_data.get("status")
        elif isinstance(email_data, str):
            address = email_data
            status = "verified"
        if not address:
            inferred = item.get("inferredEmails") or []
            if inferred:
                address = inferred[0]
                status = status or "guessed"
        if not address:
            return ocean_person_id, False, status
        if status in ("notFound", "inProgress"):
            return ocean_person_id, False, status
        return ocean_person_id, address, status

    def _detect_webhook_payload_type(self, payload):
        if not isinstance(payload, dict):
            return "unknown"

        results = payload.get("results")
        if isinstance(results, list) and results:
            first = results[0] or {}
            if "email" in first:
                return "reveal_emails"
            if "phone" in first:
                return "reveal_phones"

        ocean_id = payload.get("id") or payload.get("personId")
        if ocean_id:
            has_email = payload.get("email") is not None
            has_phone = payload.get("phone") is not None
            if has_email and has_phone:
                return "enrich_person"
            if has_email:
                return "reveal_emails"
            if has_phone:
                return "reveal_phones"
            return "enrich_person"

        if isinstance(results, dict):
            for value in results.values():
                if isinstance(value, dict) and value.get("company") is not None:
                    return "enrich_companies"
                if isinstance(value, dict) and value.get("person") is not None:
                    return "enrich_people"
        if payload.get("people"):
            return "enrich_people"
        return "unknown"

    def _find_partners_and_leads_for_ocean_person(self, ocean_person_id, person_hint=None):
        Partner = self.env["res.partner"].sudo()
        Lead = self.env["crm.lead"].sudo()
        partners = Partner.search([("ocean_person_id", "=", ocean_person_id)])
        leads = Lead.search([("ocean_person_id", "=", ocean_person_id)])

        if partners or leads or not person_hint:
            return partners, leads

        linkedin = (person_hint.get("linkedinUrl") or "").strip()
        if linkedin and "linkedin_url" in Partner._fields:
            handle = self.linkedin_handle_from_url(linkedin)
            if handle:
                partners = Partner.search([("linkedin_url", "ilike", handle)], limit=5)

        domain = (person_hint.get("domain") or "").lower().replace("www.", "")
        name = (person_hint.get("name") or "").strip()
        if not partners and domain and name:
            partners = Partner.search(
                [
                    ("name", "ilike", name),
                    "|",
                    ("website", "ilike", domain),
                    ("email", "ilike", "@%s" % domain),
                ],
                limit=5,
            )
        if not leads and domain and name:
            leads = Lead.search(
                [
                    ("contact_name", "ilike", name),
                    "|",
                    ("website", "ilike", domain),
                    ("email_from", "ilike", "@%s" % domain),
                ],
                limit=5,
            )
        return partners, leads

    def _partner_vals_from_person(self, person):
        vals = {}
        email = self.extract_person_email(person)
        phone = self.extract_person_phone(person)
        title = person.get("jobTitle") or person.get("jobTitleEnglish")
        linkedin = person.get("linkedinUrl")
        domain = person.get("domain")
        if email:
            vals["email"] = email
        if phone:
            vals["phone"] = phone
        if title:
            vals["function"] = title
        if linkedin and "linkedin_url" in self.env["res.partner"]._fields:
            vals["linkedin_url"] = linkedin
        if domain:
            vals["website"] = "https://%s" % domain
        ocean_id = person.get("id")
        if ocean_id:
            vals["ocean_person_id"] = ocean_id
        first_name, last_name = self.split_person_name(person)
        if "firstname" in self.env["res.partner"]._fields:
            if first_name:
                vals["firstname"] = first_name
            if last_name:
                vals["lastname"] = last_name
        elif person.get("name"):
            vals["name"] = person["name"]
        return vals

    def _lead_vals_from_person(self, person):
        vals = {}
        email = self.extract_person_email(person)
        phone = self.extract_person_phone(person)
        title = person.get("jobTitle") or person.get("jobTitleEnglish")
        domain = person.get("domain")
        if email:
            vals["email_from"] = email
        if phone:
            vals["phone"] = phone
        if title:
            vals["function"] = title
        if domain:
            vals["website"] = "https://%s" % domain
        ocean_id = person.get("id")
        if ocean_id:
            vals["ocean_person_id"] = ocean_id
        return vals

    def _update_records_for_ocean_person(
        self, ocean_person_id, partner_vals, lead_vals=None, person_hint=None, target_type=None
    ):
        self.ensure_one()
        if not ocean_person_id:
            return 0
        updated = 0
        Target = self.env["ocean.webhook.target"].sudo()
        target_domain = [
            ("instance_id", "=", self.id),
            ("ocean_person_id", "=", ocean_person_id),
            ("active", "=", True),
        ]
        if target_type:
            target_domain.append(("target_type", "=", target_type))
        targets = Target.search(target_domain)

        if targets:
            for target in targets:
                if target_type and target.target_type != target_type:
                    continue
                target_updated = False
                if partner_vals and target.partner_id:
                    pvals = dict(partner_vals)
                    if "ocean_person_id" not in pvals:
                        pvals["ocean_person_id"] = ocean_person_id
                    target.partner_id.write(pvals)
                    target_updated = True
                    updated += 1
                lvals = lead_vals or partner_vals
                if lvals and target.lead_id:
                    lead_write = {}
                    for key in ("email_from", "phone", "function", "website", "ocean_person_id"):
                        if key in lvals:
                            lead_write[key] = lvals[key]
                    if "email" in lvals and "email_from" not in lead_write:
                        lead_write["email_from"] = lvals["email"]
                    if "ocean_person_id" not in lead_write:
                        lead_write["ocean_person_id"] = ocean_person_id
                    if lead_write:
                        target.lead_id.write(lead_write)
                        target_updated = True
                        updated += 1
                if target_updated:
                    target.active = False
            if updated:
                return updated

        partners, leads = self._find_partners_and_leads_for_ocean_person(
            ocean_person_id, person_hint=person_hint
        )
        if partner_vals and partners:
            if "ocean_person_id" not in partner_vals:
                partner_vals = dict(partner_vals, ocean_person_id=ocean_person_id)
            partners.write(partner_vals)
            updated += len(partners)
        lead_vals = lead_vals or partner_vals
        if lead_vals and leads:
            lead_write = {}
            for key in ("email_from", "phone", "function", "website", "ocean_person_id"):
                if key in lead_vals:
                    lead_write[key] = lead_vals[key]
            if "email" in lead_vals and "email_from" not in lead_write:
                lead_write["email_from"] = lead_vals["email"]
            if "ocean_person_id" not in lead_write:
                lead_write["ocean_person_id"] = ocean_person_id
            if lead_write:
                leads.write(lead_write)
                updated += len(leads)
        return updated

    def _iter_reveal_email_items(self, payload):
        results = payload.get("results")
        if isinstance(results, list):
            for item in results:
                if isinstance(item, dict):
                    yield item
            return
        if isinstance(payload, dict) and (
            payload.get("email") is not None or payload.get("personId") or payload.get("id")
        ):
            yield payload

    def _apply_reveal_emails_payload(self, payload):
        updated = 0
        skipped = 0
        for item in self._iter_reveal_email_items(payload):
            ocean_person_id, address, status = self.extract_reveal_email(item)
            if not ocean_person_id:
                skipped += 1
                continue
            if not address:
                skipped += 1
                continue
            partner_vals = {"email": address}
            updated += self._update_records_for_ocean_person(
                ocean_person_id,
                partner_vals,
                {"email_from": address},
                person_hint=item,
                target_type="email",
            )
        return updated, skipped

    def _iter_reveal_phone_items(self, payload):
        results = payload.get("results")
        if isinstance(results, list):
            for item in results:
                if isinstance(item, dict):
                    yield item
            return
        if isinstance(payload, dict) and (
            payload.get("phone") is not None or payload.get("personId") or payload.get("id")
        ):
            yield payload

    def _apply_reveal_phones_payload(self, payload):
        updated = 0
        for item in self._iter_reveal_phone_items(payload):
            ocean_person_id = item.get("personId") or item.get("id")
            phone_data = item.get("phone") or {}
            numbers = phone_data.get("numbers") or []
            if not numbers or phone_data.get("status") == "notFound":
                continue
            partner_vals = {"phone": numbers[0]}
            updated += self._update_records_for_ocean_person(
                ocean_person_id,
                partner_vals,
                {"phone": numbers[0]},
                person_hint=item,
                target_type="phone",
            )
        return updated

    def _apply_enrich_person_payload(self, payload):
        updated = 0
        ocean_person_id = payload.get("id") or payload.get("personId")
        if not ocean_person_id:
            return 0

        _, address, _status = self.extract_reveal_email(payload)
        if address:
            updated += self._update_records_for_ocean_person(
                ocean_person_id,
                {"email": address},
                {"email_from": address},
                person_hint=payload,
                target_type="email",
            )

        phone_data = payload.get("phone") or {}
        numbers = phone_data.get("numbers") or []
        if numbers and phone_data.get("status") not in ("notFound", "inProgress"):
            updated += self._update_records_for_ocean_person(
                ocean_person_id,
                {"phone": numbers[0]},
                {"phone": numbers[0]},
                person_hint=payload,
                target_type="phone",
            )

        if updated:
            return updated

        partner_vals = self._partner_vals_from_person(payload)
        lead_vals = self._lead_vals_from_person(payload)
        return self._update_records_for_ocean_person(
            ocean_person_id,
            partner_vals,
            lead_vals,
            person_hint=payload,
        )

    def _apply_enrich_people_payload(self, payload):
        updated = 0
        people = payload.get("people") or []
        for item in people:
            if not isinstance(item, dict):
                continue
            person = item.get("person") or item
            if person.get("id"):
                updated += self._apply_enrich_person_payload(person)
        results = payload.get("results")
        if isinstance(results, dict):
            for value in results.values():
                if not isinstance(value, dict):
                    continue
                person = value.get("person")
                if person and person.get("id"):
                    updated += self._apply_enrich_person_payload(person)
        return updated

    def _apply_enrich_companies_payload(self, payload):
        Partner = self.env["res.partner"].sudo()
        updated = 0
        results = payload.get("results") or {}
        if not isinstance(results, dict):
            return 0
        for mapping_key, value in results.items():
            if not isinstance(value, dict) or value.get("status") != "found":
                continue
            company = value.get("company") or {}
            domain = (company.get("domain") or company.get("rootUrl") or "").replace(
                "www.", ""
            )
            if not domain:
                continue
            partners = Partner.search(
                [
                    "|",
                    ("website", "ilike", domain),
                    ("email", "ilike", "@%s" % domain),
                ]
            )
            vals = {}
            if company.get("name"):
                vals["name"] = company["name"]
            if domain:
                vals["website"] = "https://%s" % domain
            if vals and partners:
                partners.write(vals)
                updated += len(partners)
        return updated

    def process_webhook_payload(self, payload):
        """Process an incoming Ocean.io webhook and update matching Odoo records."""
        self.ensure_one()
        payload_type = self._detect_webhook_payload_type(payload)
        log_vals = {
            "instance_id": self.id,
            "payload_type": payload_type,
            "payload_json": json.dumps(payload, indent=2)[:500000],
            "state": "received",
        }
        log = self.env["ocean.webhook.log"].sudo().create(log_vals)
        try:
            skipped = 0
            if payload_type == "reveal_emails":
                updated, skipped = self._apply_reveal_emails_payload(payload)
            elif payload_type == "reveal_phones":
                updated = self._apply_reveal_phones_payload(payload)
            elif payload_type == "enrich_companies":
                updated = self._apply_enrich_companies_payload(payload)
            elif payload_type == "enrich_people":
                updated = self._apply_enrich_people_payload(payload)
            elif payload_type == "enrich_person":
                updated = self._apply_enrich_person_payload(payload)
            else:
                updated = 0
            message = _("%(count)s record(s) updated.") % {"count": updated}
            if updated == 0:
                if payload_type == "reveal_emails" and skipped:
                    message = _(
                        "Email webhook received but Ocean.io returned no usable email "
                        "(%(skipped)s result(s) with status notFound or inProgress). "
                        "Try Reveal Emails again or check credits."
                    ) % {"skipped": skipped}
                else:
                    message = _(
                        "Webhook received (%(type)s) but no matching Odoo records were updated. "
                        "On People Lookup, link an Odoo Contact before requesting reveal, then "
                        "check that the contact has the Ocean person ID stored."
                    ) % {"type": payload_type}
            log.write(
                {
                    "state": "processed",
                    "message": message,
                    "records_updated": updated,
                }
            )
            _logger.info(
                "Ocean.io webhook processed for instance %s (%s): %s",
                self.id,
                payload_type,
                message,
            )
            return log
        except Exception as err:
            log.write({"state": "error", "message": str(err)[:255]})
            raise
