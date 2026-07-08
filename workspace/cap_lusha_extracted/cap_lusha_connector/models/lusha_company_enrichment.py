# -*- coding: utf-8 -*-
import json
from urllib.parse import urlparse

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class LushaCompanyEnrichment(models.TransientModel):
    _name = "lusha.company.enrichment"
    _description = "Lusha Company Enrichment"

    instance_id = fields.Many2one(
        "lusha.instance",
        string="Lusha Instance",
        required=True,
        default=lambda self: self.env["lusha.instance"].get_company_instance(),
    )
    partner_id = fields.Many2one("res.partner", string="Odoo Contact")
    lusha_company_id = fields.Char(string="Lusha Company ID")
    company_name = fields.Char(string="Company Name")
    company_domain = fields.Char(string="Company Domain")

    state = fields.Selection(
        [("draft", "Draft"), ("done", "Enriched"), ("no_match", "No Match"), ("error", "Error")],
        default="draft",
        readonly=True,
    )
    result_message = fields.Char(string="Result", readonly=True)
    enriched_at = fields.Datetime(string="Enriched On", readonly=True)

    lusha_company_id_result = fields.Char(string="Lusha Company ID", readonly=True)
    enriched_name = fields.Char(string="Company Name", readonly=True)
    enriched_domain = fields.Char(string="Domain", readonly=True)
    enriched_industry = fields.Char(string="Industry", readonly=True)
    enriched_size = fields.Char(string="Company Size", readonly=True)
    enriched_revenue = fields.Char(string="Revenue Range", readonly=True)
    enriched_country = fields.Char(string="HQ Country", readonly=True)
    response_json = fields.Text(string="Raw Response", readonly=True)
    apply_overwrite = fields.Boolean(string="Overwrite Existing Fields")

    @api.model
    def _domain_from_website(self, website):
        website = (website or "").strip()
        if not website:
            return False
        if "://" not in website:
            website = "https://%s" % website
        host = urlparse(website).hostname or ""
        return host[4:] if host.startswith("www.") else host

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        partner_id = self.env.context.get("default_partner_id")
        if partner_id:
            partner = self.env["res.partner"].browse(partner_id)
            vals.setdefault("company_name", partner.name)
            domain = self._domain_from_website(partner.website)
            if not domain and partner.email and "@" in partner.email:
                domain = partner.email.split("@", 1)[1].lower()
            vals.setdefault("company_domain", domain)
        return vals

    def _validate_inputs(self):
        self.ensure_one()
        if not (
            (self.lusha_company_id or "").strip()
            or (self.company_name or "").strip()
            or (self.company_domain or "").strip()
        ):
            raise ValidationError(
                _("Provide a Lusha company ID, company name, or company domain.")
            )

    def _prepare_company_payload(self):
        self.ensure_one()
        company = {}
        if self.lusha_company_id:
            company["id"] = self.lusha_company_id.strip()
        if self.company_name:
            company["name"] = self.company_name.strip()
        if self.company_domain:
            company["domain"] = self.env["lusha.instance"].normalize_domain(
                self.company_domain
            )
        return company

    def _apply_enrichment_response(self, response):
        self.ensure_one()
        results = response.get("results") or []
        company = results[0] if results else {}
        if company.get("error") or not company.get("id"):
            error = company.get("error") or {}
            self.write(
                {
                    "state": "no_match",
                    "result_message": error.get("message")
                    or _("Lusha did not find a matching company."),
                    "enriched_at": fields.Datetime.now(),
                    "response_json": json.dumps(response, indent=2)[:50000],
                }
            )
            return False

        location = company.get("location") or company.get("hq") or {}
        self.write(
            {
                "state": "done",
                "result_message": _("Company enriched successfully."),
                "enriched_at": fields.Datetime.now(),
                "lusha_company_id_result": company.get("id"),
                "enriched_name": company.get("name"),
                "enriched_domain": (company.get("domain") or "").replace("www.", ""),
                "enriched_industry": company.get("industry") or company.get("mainIndustry"),
                "enriched_size": company.get("employees") or company.get("size"),
                "enriched_revenue": company.get("revenueRange") or company.get("revenue"),
                "enriched_country": location.get("country"),
                "response_json": json.dumps(response, indent=2)[:50000],
            }
        )
        return True

    def action_enrich(self):
        self.ensure_one()
        if not self.instance_id:
            raise UserError(_("Select a Lusha instance."))
        self._validate_inputs()
        payload = {"companies": [self._prepare_company_payload()]}
        try:
            response = self.instance_id.search_and_enrich_companies(payload)
            matched = self._apply_enrichment_response(response)
        except UserError as err:
            self.write(
                {
                    "state": "error",
                    "result_message": str(err)[:255],
                    "enriched_at": fields.Datetime.now(),
                }
            )
            raise

        if not matched:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Lusha"),
                    "message": self.result_message,
                    "type": "warning",
                    "sticky": False,
                },
            }
        return {
            "type": "ir.actions.act_window",
            "res_model": "lusha.company.enrichment",
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }

    def action_apply_to_partner(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("Link an Odoo contact before applying company data."))
        if self.state != "done":
            raise UserError(_("Run enrichment successfully before applying data."))

        partner = self.partner_id
        vals = {}
        if self.apply_overwrite or not partner.name:
            if self.enriched_name:
                vals["name"] = self.enriched_name
        website = "https://%s" % self.enriched_domain if self.enriched_domain else False
        if website and (self.apply_overwrite or not partner.website):
            vals["website"] = website
        if self.lusha_company_id_result and (
            self.apply_overwrite or not getattr(partner, "lusha_company_id", False)
        ):
            if "lusha_company_id" in partner._fields:
                vals["lusha_company_id"] = self.lusha_company_id_result

        if not vals:
            raise UserError(_("Nothing was updated on the contact."))

        partner.write(vals)
        return {
            "type": "ir.actions.act_window",
            "name": partner.display_name,
            "res_model": "res.partner",
            "view_mode": "form",
            "res_id": partner.id,
            "target": "current",
        }
