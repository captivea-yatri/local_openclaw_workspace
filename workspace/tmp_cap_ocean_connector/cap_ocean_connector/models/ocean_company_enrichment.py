# -*- coding: utf-8 -*-
import json
from urllib.parse import urlparse

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class OceanCompanyEnrichment(models.TransientModel):
    _name = "ocean.company.enrichment"
    _description = "Ocean.io Company Enrichment"

    instance_id = fields.Many2one(
        "ocean.instance",
        string="Ocean.io Instance",
        required=True,
        default=lambda self: self.env["ocean.instance"].get_company_instance(),
    )
    partner_id = fields.Many2one("res.partner", string="Odoo Contact")
    domain = fields.Char(
        string="Company Domain",
        help="Example: company.com (without www.)",
    )
    domains_text = fields.Char(
        string="Additional Domains",
        help="Comma-separated domains for batch enrichment.",
    )
    state = fields.Selection(
        [("draft", "Draft"), ("submitted", "Submitted"), ("error", "Error")],
        default="draft",
        readonly=True,
    )
    result_message = fields.Char(string="Result", readonly=True)
    submitted_at = fields.Datetime(string="Submitted On", readonly=True)
    response_json = fields.Text(string="Raw Response", readonly=True)

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
            domain = self._domain_from_website(partner.website)
            if not domain and partner.email and "@" in partner.email:
                domain = partner.email.split("@", 1)[1].lower()
            vals.setdefault("domain", domain)
        return vals

    @staticmethod
    def _split_csv(value):
        return [item.strip().lower().replace("www.", "") for item in (value or "").split(",") if item.strip()]

    def _collect_domains(self):
        self.ensure_one()
        domains = []
        if self.domain:
            domains.append(self.domain.strip().lower().replace("www.", ""))
        domains.extend(self._split_csv(self.domains_text))
        unique_domains = []
        for domain in domains:
            if domain and domain not in unique_domains:
                unique_domains.append(domain)
        if not unique_domains:
            raise ValidationError(_("Provide at least one company domain to enrich."))
        if len(unique_domains) > 10000:
            raise ValidationError(_("Company enrichment supports up to 10,000 domains per request."))
        return unique_domains

    def action_enrich_companies(self):
        self.ensure_one()
        if not self.instance_id:
            raise UserError(_("Select an Ocean.io instance."))

        domains = self._collect_domains()
        company_data_mapping = {
            "odoo-partner-%s" % index: {"company": {"domain": domain}}
            for index, domain in enumerate(domains, start=1)
        }
        try:
            response = self.instance_id.enrich_companies(company_data_mapping)
        except UserError as err:
            self.write(
                {
                    "state": "error",
                    "result_message": str(err)[:255],
                    "submitted_at": fields.Datetime.now(),
                }
            )
            raise

        message = _(
            "Company enrichment submitted for %(count)s domain(s). "
            "Results will be delivered to your webhook URL."
        ) % {"count": len(domains)}
        self.write(
            {
                "state": "submitted",
                "result_message": message,
                "submitted_at": fields.Datetime.now(),
                "response_json": json.dumps(response, indent=2)[:50000],
            }
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Ocean.io"),
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }
