# -*- coding: utf-8 -*-
import hashlib
import hmac
import json
import logging
import uuid
from urllib.parse import urlencode

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..const import (
    LUSHA_API_BASE_URL,
    LUSHA_API_KEY_HEADER,
    LUSHA_REQUEST_TIMEOUT,
    LUSHA_WEBHOOK_PATH,
)

_logger = logging.getLogger(__name__)


class LushaInstance(models.Model):
    _name = "lusha.instance"
    _description = "Lusha connection"
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
        default=LUSHA_API_BASE_URL,
        help="Lusha REST API base URL. Default: https://api.lusha.com",
    )
    api_key = fields.Char(
        string="API Key",
        required=True,
        help="Generate an API key in the Lusha dashboard under API settings.",
    )
    public_base_url = fields.Char(
        string="Public HTTPS URL (optional)",
        help="Public HTTPS address where Lusha can reach Odoo for webhooks. "
        "Leave empty when System Parameters → web.base.url is already HTTPS.",
    )
    database = fields.Char(
        string="Odoo Database",
        readonly=True,
        help="Appended as ?db=... on the webhook URL for multi-database routing.",
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
    credit_total = fields.Integer(string="Total Credits", readonly=True)
    credit_used = fields.Integer(string="Used Credits", readonly=True)
    credit_remaining = fields.Integer(string="Remaining Credits", readonly=True)
    plan_category = fields.Char(string="Plan", readonly=True)

    

  
    # -------------------------------------------------------------------------
    # HTTP client
    # -------------------------------------------------------------------------

    def _get_api_key(self):
        self.ensure_one()
        api_key = (self.api_key or "").strip()
        if not api_key:
            raise UserError(_("Set a Lusha API key before calling the API."))
        return api_key

    def _build_url(self, path):
        self.ensure_one()
        base = (self.api_base_url or LUSHA_API_BASE_URL).rstrip("/")
        if not path.startswith("/"):
            path = "/" + path
        return base + path

    def _build_headers(self, extra_headers=None):
        self.ensure_one()
        headers = {
            LUSHA_API_KEY_HEADER: self._get_api_key(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def lusha_api_request(self, method, path, json_body=None, params=None, timeout=None):
        """Call the Lusha REST API with api_key header authentication."""
        self.ensure_one()
        url = self._build_url(path)
        kwargs = {
            "method": method.upper(),
            "url": url,
            "headers": self._build_headers(),
            "timeout": timeout or LUSHA_REQUEST_TIMEOUT,
        }
        if params:
            kwargs["params"] = params
        if json_body is not None:
            kwargs["json"] = json_body

        _logger.info("Lusha %s %s", method.upper(), url)
        try:
            response = requests.request(**kwargs)
        except requests.RequestException as err:
            raise UserError(
                _(
                    "Could not reach Lusha at %(url)s.\n\nNetwork error: %(error)s"
                )
                % {"url": url, "error": err}
            ) from err

        raw_text = response.text or ""
        try:
            body = response.json() if response.content else {}
        except Exception:
            body = {}

        if response.status_code >= 400:
            message = self._format_api_error(response.status_code, body, raw_text)
            _logger.warning(
                "Lusha API error %s for %s %s: %s",
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
            detail = body.get("message")
            errors = body.get("errors")
            if errors:
                detail = "%s (%s)" % (detail or "", "; ".join(str(e) for e in errors))
            if not detail:
                detail = json.dumps(body) if body else raw_text[:2000]
        else:
            detail = str(body)

        hints = {
            401: _("Invalid or missing API key. Verify the key in the Lusha dashboard."),
            402: _("Insufficient credits. Check your Lusha account balance."),
            403: _("Account inactive or access denied. Contact support@lusha.com."),
            429: _("Rate limit exceeded. Wait and try again."),
            451: _("Request blocked due to GDPR regulations."),
        }
        hint = hints.get(status_code, "")
        msg = _("Lusha API error (%(status)s): %(detail)s") % {
            "status": status_code,
            "detail": str(detail)[:2000],
        }
        if hint:
            msg = "%s\n\n%s" % (msg, hint)
        return msg

    # -------------------------------------------------------------------------
    # Account
    # -------------------------------------------------------------------------

    def get_account_usage(self):
        """GET /v3/account/usage — credits, rate limits, plan, pricing."""
        self.ensure_one()
        return self.lusha_api_request("GET", "/v3/account/usage")

    # -------------------------------------------------------------------------
    # Search
    # -------------------------------------------------------------------------

    def search_contacts(self, payload):
        """POST /v3/contacts/search — lookup contacts by identifier (preview only)."""
        self.ensure_one()
        return self.lusha_api_request("POST", "/v3/contacts/search", json_body=payload)

    def search_companies(self, payload):
        """POST /v3/companies/search — lookup companies by identifier (preview only)."""
        self.ensure_one()
        return self.lusha_api_request("POST", "/v3/companies/search", json_body=payload)

    # -------------------------------------------------------------------------
    # Enrich
    # -------------------------------------------------------------------------

    def enrich_contacts(self, payload):
        """POST /v3/contacts/enrich — reveal emails/phones for contact IDs."""
        self.ensure_one()
        return self.lusha_api_request("POST", "/v3/contacts/enrich", json_body=payload)

    def enrich_companies(self, payload):
        """POST /v3/companies/enrich — reveal full company data by ID."""
        self.ensure_one()
        return self.lusha_api_request("POST", "/v3/companies/enrich", json_body=payload)

    # -------------------------------------------------------------------------
    # Search & Enrich
    # -------------------------------------------------------------------------

    def search_and_enrich_contacts(self, payload):
        """POST /v3/contacts/search-and-enrich — find and reveal contact data."""
        self.ensure_one()
        return self.lusha_api_request("POST", "/v3/contacts/search-and-enrich", json_body=payload)

    def search_and_enrich_companies(self, payload):
        """POST /v3/companies/search-and-enrich — find and reveal company data."""
        self.ensure_one()
        return self.lusha_api_request("POST", "/v3/companies/search-and-enrich", json_body=payload)

    # -------------------------------------------------------------------------
    # Prospecting
    # -------------------------------------------------------------------------

    def prospect_contacts(self, payload):
        """POST /v3/contacts/prospecting — filter-based contact search."""
        self.ensure_one()
        return self.lusha_api_request("POST", "/v3/contacts/prospecting", json_body=payload)

    def prospect_companies(self, payload):
        """POST /v3/companies/prospecting — filter-based company search."""
        self.ensure_one()
        return self.lusha_api_request("POST", "/v3/companies/prospecting", json_body=payload)

    # -------------------------------------------------------------------------
    # Lookalikes
    # -------------------------------------------------------------------------

    def contact_lookalikes(self, payload):
        """POST /v3/contacts/lookalike — AI contact recommendations."""
        self.ensure_one()
        return self.lusha_api_request("POST", "/v3/contacts/lookalike", json_body=payload)

    def company_lookalikes(self, payload):
        """POST /v3/companies/lookalike — AI company recommendations."""
        self.ensure_one()
        return self.lusha_api_request("POST", "/v3/companies/lookalike", json_body=payload)

    # -------------------------------------------------------------------------
    # Signals
    # -------------------------------------------------------------------------

    def get_contact_signals(self, payload):
        """POST /v3/contacts/signals — job changes and promotions."""
        self.ensure_one()
        return self.lusha_api_request("POST", "/v3/contacts/signals", json_body=payload)

    def get_company_signals(self, payload):
        """POST /v3/companies/signals — hiring, headcount, news signals."""
        self.ensure_one()
        return self.lusha_api_request("POST", "/v3/companies/signals", json_body=payload)

    def get_contact_signal_types(self):
        """GET /v3/contacts/signals/types."""
        self.ensure_one()
        return self.lusha_api_request("GET", "/v3/contacts/signals/types")

    def get_company_signal_types(self):
        """GET /v3/companies/signals/types."""
        self.ensure_one()
        return self.lusha_api_request("GET", "/v3/companies/signals/types")

    def get_company_signal_filters(self):
        """GET /v3/companies/signals/filters."""
        self.ensure_one()
        return self.lusha_api_request("GET", "/v3/companies/signals/filters")

    def get_company_signal_filter_values(self, filter_type, params=None):
        """GET /v3/companies/signals/filters/{filterType}."""
        self.ensure_one()
        return self.lusha_api_request(
            "GET",
            "/v3/companies/signals/filters/%s" % filter_type,
            params=params,
        )

    # -------------------------------------------------------------------------
    # Prospecting filters
    # -------------------------------------------------------------------------

    def get_contact_prospecting_filter_types(self):
        """GET /v3/contacts/prospecting/filters."""
        self.ensure_one()
        return self.lusha_api_request("GET", "/v3/contacts/prospecting/filters")

    def get_contact_prospecting_filter_values(self, filter_type, params=None):
        """GET /v3/contacts/prospecting/filters/{filterType}."""
        self.ensure_one()
        return self.lusha_api_request(
            "GET",
            "/v3/contacts/prospecting/filters/%s" % filter_type,
            params=params,
        )

    def get_company_prospecting_filter_types(self):
        """GET /v3/companies/prospecting/filters."""
        self.ensure_one()
        return self.lusha_api_request("GET", "/v3/companies/prospecting/filters")

    def get_company_prospecting_filter_values(self, filter_type, params=None):
        """GET /v3/companies/prospecting/filters/{filterType}."""
        self.ensure_one()
        return self.lusha_api_request(
            "GET",
            "/v3/companies/prospecting/filters/%s" % filter_type,
            params=params,
        )



    # -------------------------------------------------------------------------
    # Data extraction helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def extract_contact_email(contact):
        emails = contact.get("emails") or []
        for item in emails:
            if isinstance(item, dict) and item.get("email"):
                return item["email"], item.get("type"), item.get("confidence")
        return False, False, False

    @staticmethod
    def extract_contact_phone(contact):
        phones = contact.get("phones") or []
        for item in phones:
            if isinstance(item, dict) and item.get("number"):
                return item["number"]
        return False

    @staticmethod
    def extract_job_title(contact):
        job = contact.get("jobTitle") or {}
        if isinstance(job, dict):
            return job.get("title")
        return False

    @staticmethod
    def extract_company_name(contact):
        company = contact.get("company") or {}
        if isinstance(company, dict):
            return company.get("name")
        return False

    @staticmethod
    def extract_company_domain(contact):
        company = contact.get("company") or {}
        if isinstance(company, dict):
            domain = company.get("domain") or ""
            return domain.replace("www.", "")
        return False

    @staticmethod
    def extract_linkedin_url(contact):
        social = contact.get("socialLinks") or {}
        if isinstance(social, dict):
            return social.get("linkedin")
        return False

    @staticmethod
    def normalize_domain(domain):
        domain = (domain or "").strip().lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain

  

    # -------------------------------------------------------------------------
    # UI actions
    # -------------------------------------------------------------------------

    def action_test_connection(self):
        self.ensure_one()
        try:
            payload = self.get_account_usage()
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
        plan = payload.get("plan") or {}
        success_message = _("Lusha connection successful.")
        self.write(
            {
                "last_connection_test": fields.Datetime.now(),
                "connection_status": "connected",
                "connection_message": success_message,
                "credit_total": int(credits.get("total") or 0),
                "credit_used": int(credits.get("used") or 0),
                "credit_remaining": int(credits.get("remaining") or 0),
                "plan_category": plan.get("category") or False,
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
            "name": _("Contact Enrichment"),
            "type": "ir.actions.act_window",
            "res_model": "lusha.people.enrichment",
            "view_mode": "form",
            "target": "new",
            "context": {"default_instance_id": self.id},
        }

    def action_open_company_enrichment(self):
        self.ensure_one()
        return {
            "name": _("Company Enrichment"),
            "type": "ir.actions.act_window",
            "res_model": "lusha.company.enrichment",
            "view_mode": "form",
            "target": "new",
            "context": {"default_instance_id": self.id},
        }

    def action_open_lead_prospect(self):
        self.ensure_one()
        return {
            "name": _("Lead Prospecting"),
            "type": "ir.actions.act_window",
            "res_model": "lusha.lead.prospect",
            "view_mode": "form",
            "target": "new",
            "context": {"default_instance_id": self.id},
        }

 

    @api.model
    def get_company_instance(self, company=None):
        company = company or self.env.company
        return self.search(
            [("company_id", "=", company.id), ("active", "=", True)],
            limit=1,
        )
