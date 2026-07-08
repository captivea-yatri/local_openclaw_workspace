# -*- coding: utf-8 -*-
import json
from urllib.parse import urlparse

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class LushaPeopleEnrichment(models.TransientModel):
    _name = "lusha.people.enrichment"
    _description = "Lusha Contact Enrichment"

    instance_id = fields.Many2one(
        "lusha.instance",
        string="Lusha Instance",
        required=True,
        default=lambda self: self.env["lusha.instance"].get_company_instance(),
    )
    partner_id = fields.Many2one("res.partner", string="Odoo Contact")
    lusha_contact_id = fields.Char(string="Lusha Contact ID")
    linkedin_url = fields.Char(string="LinkedIn URL")
    email = fields.Char(string="Email")
    first_name = fields.Char(string="First Name")
    last_name = fields.Char(string="Last Name")
    company_name = fields.Char(string="Company Name")
    company_domain = fields.Char(string="Company Domain")

    reveal_emails = fields.Boolean(string="Reveal Emails", default=True)
    reveal_phones = fields.Boolean(string="Reveal Phones")
    apply_overwrite = fields.Boolean(string="Overwrite Existing Fields")

    state = fields.Selection(
        [("draft", "Draft"), ("done", "Enriched"), ("no_match", "No Match"), ("error", "Error")],
        default="draft",
        readonly=True,
    )
    result_message = fields.Char(string="Result", readonly=True)
    enriched_at = fields.Datetime(string="Enriched On", readonly=True)

    lusha_contact_id_result = fields.Char(string="Lusha Contact ID", readonly=True)
    enriched_email = fields.Char(string="Email", readonly=True)
    enriched_phone = fields.Char(string="Phone", readonly=True)
    enriched_title = fields.Char(string="Job Title", readonly=True)
    enriched_linkedin_url = fields.Char(string="LinkedIn", readonly=True)
    enriched_company_name = fields.Char(string="Company", readonly=True)
    enriched_company_domain = fields.Char(string="Company Domain", readonly=True)
    enriched_city = fields.Char(string="City", readonly=True)
    enriched_country = fields.Char(string="Country", readonly=True)
    email_confidence = fields.Char(string="Email Confidence", readonly=True)
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
            vals.setdefault("lusha_contact_id", partner.lusha_contact_id)
            vals.setdefault("email", partner.email)
            vals.setdefault("company_name", partner.commercial_company_name or partner.parent_id.name)
            firstname = getattr(partner, "firstname", None)
            lastname = getattr(partner, "lastname", None)
            if firstname or lastname:
                vals.setdefault("first_name", firstname)
                vals.setdefault("last_name", lastname)
            elif partner.name:
                parts = partner.name.strip().split(None, 1)
                vals.setdefault("first_name", parts[0])
                if len(parts) > 1:
                    vals.setdefault("last_name", parts[1])
            domain = self._domain_from_website(partner.website)
            if not domain and partner.email and "@" in partner.email:
                domain = partner.email.split("@", 1)[1].lower()
            vals.setdefault("company_domain", domain)
            linkedin = getattr(partner, "linkedin_url", None) or getattr(partner, "linkedin", None)
            if linkedin:
                vals.setdefault("linkedin_url", linkedin)
        return vals

    def _validate_inputs(self):
        self.ensure_one()
        has_id = bool((self.lusha_contact_id or "").strip())
        has_email = bool((self.email or "").strip())
        has_linkedin = bool((self.linkedin_url or "").strip())
        has_name_company = bool(self.first_name and self.last_name) and bool(
            (self.company_name or "").strip() or (self.company_domain or "").strip()
        )
        if not (has_id or has_email or has_linkedin or has_name_company):
            raise ValidationError(
                _(
                    "Provide enough data for Lusha to find a contact:\n"
                    "- Lusha Contact ID, email, or LinkedIn URL\n"
                    "- OR first name + last name + company name or domain"
                )
            )

    def _prepare_contact_payload(self):
        self.ensure_one()
        contact = {}
        if self.lusha_contact_id:
            contact["id"] = self.lusha_contact_id.strip()
        if self.linkedin_url:
            contact["linkedinUrl"] = self.linkedin_url.strip()
        if self.email:
            contact["email"] = self.email.strip()
        if self.first_name:
            contact["firstName"] = self.first_name.strip()
        if self.last_name:
            contact["lastName"] = self.last_name.strip()
        if self.company_name:
            contact["companyName"] = self.company_name.strip()
        if self.company_domain:
            contact["companyDomain"] = self.env["lusha.instance"].normalize_domain(
                self.company_domain
            )
        return contact

    def _prepare_request_payload(self):
        self.ensure_one()
        payload = {"contacts": [self._prepare_contact_payload()]}
        reveal = []
        if self.reveal_emails:
            reveal.append("emails")
        if self.reveal_phones:
            reveal.append("phones")
        if reveal:
            payload["reveal"] = reveal
        return payload

    def _apply_enrichment_response(self, response):
        self.ensure_one()
        results = response.get("results") or []
        contact = results[0] if results else {}
        if contact.get("error") or not contact.get("id"):
            error = contact.get("error") or {}
            self.write(
                {
                    "state": "no_match",
                    "result_message": error.get("message")
                    or _("Lusha did not find a matching contact."),
                    "enriched_at": fields.Datetime.now(),
                    "response_json": json.dumps(response, indent=2)[:50000],
                }
            )
            return False

        Instance = self.env["lusha.instance"]
        email, _email_type, confidence = Instance.extract_contact_email(contact)
        location = contact.get("location") or {}
        self.write(
            {
                "state": "done",
                "result_message": _("Contact enriched successfully."),
                "enriched_at": fields.Datetime.now(),
                "lusha_contact_id_result": contact.get("id"),
                "enriched_email": email,
                "email_confidence": confidence,
                "enriched_phone": Instance.extract_contact_phone(contact),
                "enriched_title": Instance.extract_job_title(contact),
                "enriched_linkedin_url": Instance.extract_linkedin_url(contact),
                "enriched_company_name": Instance.extract_company_name(contact),
                "enriched_company_domain": Instance.extract_company_domain(contact),
                "enriched_city": location.get("city"),
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
        try:
            response = self.instance_id.search_and_enrich_contacts(
                self._prepare_request_payload()
            )
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
            "res_model": "lusha.people.enrichment",
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }

    @staticmethod
    def _field_is_empty(value):
        return not (value or "").strip()

    def _should_write_field(self, current_value, new_value):
        self.ensure_one()
        if self._field_is_empty(new_value):
            return False
        if self.apply_overwrite:
            return True
        return self._field_is_empty(current_value)

    def _find_country_id(self, country_name):
        if not country_name:
            return False
        Country = self.env["res.country"]
        country = Country.search([("name", "=ilike", country_name.strip())], limit=1)
        return country.id if country else False

    def action_apply_to_partner(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("Link an Odoo contact before applying enrichment data."))
        if self.state != "done":
            raise UserError(_("Run enrichment successfully before applying data to the contact."))

        partner = self.partner_id
        vals = {}
        if self._should_write_field(partner.email, self.enriched_email):
            vals["email"] = self.enriched_email
        if self._should_write_field(partner.function, self.enriched_title):
            vals["function"] = self.enriched_title
        if self._should_write_field(partner.phone, self.enriched_phone):
            vals["phone"] = self.enriched_phone
        website = (
            "https://%s" % self.enriched_company_domain if self.enriched_company_domain else False
        )
        if self._should_write_field(partner.website, website):
            vals["website"] = website
        if hasattr(partner, "linkedin_url") and self._should_write_field(
            partner.linkedin_url, self.enriched_linkedin_url
        ):
            vals["linkedin_url"] = self.enriched_linkedin_url
        if self._should_write_field(partner.city, self.enriched_city):
            vals["city"] = self.enriched_city
        country_id = self._find_country_id(self.enriched_country)
        if country_id and (self.apply_overwrite or not partner.country_id):
            vals["country_id"] = country_id
        if self.lusha_contact_id_result and (
            self.apply_overwrite or not partner.lusha_contact_id
        ):
            vals["lusha_contact_id"] = self.lusha_contact_id_result

        if not vals:
            raise UserError(_("Nothing was updated. Enable 'Overwrite existing fields' and retry."))

        partner.write(vals)
        return {
            "type": "ir.actions.act_window",
            "name": partner.display_name,
            "res_model": "res.partner",
            "view_mode": "form",
            "res_id": partner.id,
            "target": "current",
        }
