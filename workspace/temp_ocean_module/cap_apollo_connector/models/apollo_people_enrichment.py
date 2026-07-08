# -*- coding: utf-8 -*-
import json
from urllib.parse import urlparse

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ApolloPeopleEnrichment(models.TransientModel):
    _name = "apollo.people.enrichment"
    _description = "Apollo People Enrichment"

    instance_id = fields.Many2one(
        "apollo.instance",
        string="Apollo Instance",
        required=True,
        default=lambda self: self.env["apollo.instance"].get_company_instance(),
    )
    partner_id = fields.Many2one("res.partner", string="Odoo Contact")

    first_name = fields.Char(string="First Name")
    last_name = fields.Char(string="Last Name")
    name = fields.Char(string="Full Name")
    email = fields.Char(string="Email")
    organization_name = fields.Char(string="Organization")
    domain = fields.Char(
        string="Company Domain",
        help="Example: apollo.io (without www.)",
    )
    linkedin_url = fields.Char(string="LinkedIn URL")
    apollo_person_id = fields.Char(string="Apollo Person ID")

    reveal_personal_emails = fields.Boolean(
        string="Reveal Personal Emails",
        help="May consume Apollo credits. Personal emails are not returned for GDPR regions.",
    )
    reveal_phone_number = fields.Boolean(
        string="Reveal Phone Number",
        help="May consume Apollo credits. Requires a webhook URL on the Apollo instance.",
    )

    state = fields.Selection(
        [("draft", "Draft"), ("done", "Enriched"), ("no_match", "No Match"), ("error", "Error")],
        default="draft",
        readonly=True,
    )
    result_message = fields.Char(string="Result", readonly=True)
    enriched_at = fields.Datetime(string="Enriched On", readonly=True)

    apollo_person_id_result = fields.Char(string="Apollo Person ID", readonly=True)
    enriched_email = fields.Char(string="Work Email", readonly=True)
    enriched_title = fields.Char(string="Job Title", readonly=True)
    enriched_linkedin_url = fields.Char(string="LinkedIn", readonly=True)
    enriched_city = fields.Char(string="City", readonly=True)
    enriched_state = fields.Char(string="State", readonly=True)
    enriched_country = fields.Char(string="Country", readonly=True)
    enriched_organization_name = fields.Char(string="Company", readonly=True)
    enriched_organization_domain = fields.Char(string="Company Domain", readonly=True)
    enriched_phone = fields.Char(string="Phone", readonly=True)
    email_status = fields.Char(string="Email Status", readonly=True)
    enriched_first_name = fields.Char(string="Enriched First Name", readonly=True)
    enriched_last_name = fields.Char(string="Enriched Last Name", readonly=True)
    response_json = fields.Text(string="Raw Response", readonly=True)
    apply_overwrite = fields.Boolean(
        string="Overwrite Existing Fields",
        help="When enabled, Apollo values replace existing email, job title, phone, "
        "website, and location fields on the contact.",
    )

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
    def _domain_from_email(self, email):
        email = (email or "").strip()
        if "@" not in email:
            return False
        return email.split("@", 1)[1].lower()

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        partner_id = self.env.context.get("default_partner_id")
        if partner_id:
            partner = self.env["res.partner"].browse(partner_id)
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
            vals.setdefault("email", partner.email)
            vals.setdefault("organization_name", partner.commercial_company_name or partner.parent_id.name)
            domain = self._domain_from_website(partner.website)
            if not domain:
                domain = self._domain_from_email(partner.email)
            vals.setdefault("domain", domain)
            linkedin = getattr(partner, "linkedin_url", None) or getattr(partner, "linkedin", None)
            if linkedin:
                vals.setdefault("linkedin_url", linkedin)
        return vals

    def _validate_search_inputs(self):
        self.ensure_one()
        has_person_id = bool((self.apollo_person_id or "").strip())
        has_email = bool((self.email or "").strip())
        has_linkedin = bool((self.linkedin_url or "").strip())
        has_name = bool((self.name or "").strip())
        has_first_last = bool(self.first_name and self.last_name)
        has_domain = bool((self.domain or "").strip())
        has_org = bool((self.organization_name or "").strip())

        if has_person_id or has_email or has_linkedin:
            return
        if has_name and (has_domain or has_org):
            return
        if has_first_last and (has_domain or has_org or has_email):
            return
        raise ValidationError(
            _(
                "Provide enough data for Apollo to find a person:\n"
                "- Email, LinkedIn URL, or Apollo Person ID\n"
                "- OR full name + company domain\n"
                "- OR first name + last name + company domain or email"
            )
        )

    def _prepare_enrichment_params(self):
        self.ensure_one()
        params = {}
        if self.first_name:
            params["first_name"] = self.first_name.strip()
        if self.last_name:
            params["last_name"] = self.last_name.strip()
        if self.name:
            params["name"] = self.name.strip()
        if self.email:
            params["email"] = self.email.strip()
        if self.organization_name:
            params["organization_name"] = self.organization_name.strip()
        if self.domain:
            params["domain"] = self.domain.strip().lower().replace("www.", "")
        if self.linkedin_url:
            params["linkedin_url"] = self.linkedin_url.strip()
        if self.apollo_person_id:
            params["id"] = self.apollo_person_id.strip()
        if self.reveal_personal_emails:
            params["reveal_personal_emails"] = True
        if self.reveal_phone_number:
            params["reveal_phone_number"] = True
        return params

    @staticmethod
    def _phone_from_person(person):
        contact = person.get("contact") or {}
        if contact.get("sanitized_phone"):
            return contact["sanitized_phone"]
        phone_numbers = contact.get("phone_numbers") or person.get("phone_numbers") or []
        if phone_numbers:
            return phone_numbers[0].get("sanitized_number") or phone_numbers[0].get("raw_number")
        organization = person.get("organization") or {}
        primary_phone = organization.get("primary_phone") or {}
        if isinstance(primary_phone, dict):
            return primary_phone.get("sanitized_number") or primary_phone.get("number")
        return False

    def _apply_enrichment_response(self, response):
        self.ensure_one()
        person = response.get("person") or {}
        if not person.get("id") and not person.get("email"):
            self.write(
                {
                    "state": "no_match",
                    "result_message": _(
                        "Apollo did not find a matching person. Add email, LinkedIn, "
                        "or name + company domain and try again."
                    ),
                    "enriched_at": fields.Datetime.now(),
                    "response_json": json.dumps(response, indent=2)[:50000],
                }
            )
            return False

        organization = person.get("organization") or {}
        self.write(
            {
                "state": "done",
                "result_message": _("Person enriched successfully."),
                "enriched_at": fields.Datetime.now(),
                "apollo_person_id_result": person.get("id"),
                "enriched_email": person.get("email"),
                "enriched_title": person.get("title"),
                "enriched_linkedin_url": person.get("linkedin_url"),
                "enriched_city": person.get("city"),
                "enriched_state": person.get("state"),
                "enriched_country": person.get("country"),
                "enriched_organization_name": organization.get("name") or person.get("organization_name"),
                "enriched_organization_domain": organization.get("primary_domain"),
                "enriched_phone": self._phone_from_person(person),
                "email_status": person.get("email_status"),
                "enriched_first_name": person.get("first_name"),
                "enriched_last_name": person.get("last_name"),
                "response_json": json.dumps(response, indent=2)[:50000],
            }
        )
        return True

    def action_enrich(self):
        self.ensure_one()
        if not self.instance_id:
            raise UserError(_("Select an Apollo instance."))
        self._validate_search_inputs()
        try:
            response = self.instance_id.enrich_person(self._prepare_enrichment_params())
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
                    "title": _("Apollo"),
                    "message": self.result_message,
                    "type": "warning",
                    "sticky": False,
                },
            }
        if self.reveal_phone_number:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Apollo"),
                    "message": _(
                        "Person enriched. Phone numbers may arrive asynchronously on your webhook URL."
                    ),
                    "type": "success",
                    "sticky": False,
                },
            }
        return {
            "type": "ir.actions.act_window",
            "res_model": "apollo.people.enrichment",
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
        if not country:
            country = Country.search([("code", "=ilike", country_name.strip())], limit=1)
        return country.id if country else False

    def _build_partner_update_vals(self, partner):
        self.ensure_one()
        vals = {}
        updated_labels = []

        if self._should_write_field(partner.email, self.enriched_email):
            vals["email"] = self.enriched_email
            updated_labels.append(_("Email"))

        if self._should_write_field(partner.function, self.enriched_title):
            vals["function"] = self.enriched_title
            updated_labels.append(_("Job position"))

        if self.enriched_phone:
            phone_field = "phone"
            if hasattr(partner, "mobile") and partner._fields.get("mobile"):
                if self._should_write_field(partner.phone, self.enriched_phone):
                    vals["phone"] = self.enriched_phone
                    updated_labels.append(_("Phone"))
                elif self._should_write_field(partner.mobile, self.enriched_phone):
                    vals["mobile"] = self.enriched_phone
                    updated_labels.append(_("Mobile"))
            elif self._should_write_field(partner.phone, self.enriched_phone):
                vals["phone"] = self.enriched_phone
                updated_labels.append(_("Phone"))

        website_value = (
            "https://%s" % self.enriched_organization_domain
            if self.enriched_organization_domain
            else False
        )
        if self._should_write_field(partner.website, website_value):
            vals["website"] = website_value
            updated_labels.append(_("Website"))

        if hasattr(partner, "linkedin_url") and partner._fields.get("linkedin_url"):
            if self._should_write_field(partner.linkedin_url, self.enriched_linkedin_url):
                vals["linkedin_url"] = self.enriched_linkedin_url
                updated_labels.append(_("LinkedIn"))

        first = self.enriched_first_name or self.first_name
        last = self.enriched_last_name or self.last_name
        if hasattr(partner, "firstname") and partner._fields.get("firstname"):
            if first and self._should_write_field(partner.firstname, first):
                vals["firstname"] = first
                updated_labels.append(_("First name"))
            if last and self._should_write_field(partner.lastname, last):
                vals["lastname"] = last
                updated_labels.append(_("Last name"))
        elif first or last:
            full_name = " ".join(part for part in (first, last) if part)
            if full_name and self._should_write_field(partner.name, full_name):
                vals["name"] = full_name
                updated_labels.append(_("Name"))

        if self._should_write_field(partner.city, self.enriched_city):
            vals["city"] = self.enriched_city
            updated_labels.append(_("City"))

        country_id = self._find_country_id(self.enriched_country)
        if country_id and (self.apply_overwrite or not partner.country_id):
            vals["country_id"] = country_id
            updated_labels.append(_("Country"))

        if self.apollo_person_id_result and (
            self.apply_overwrite or not partner.apollo_person_id
        ):
            vals["apollo_person_id"] = self.apollo_person_id_result
            updated_labels.append(_("Apollo person ID"))

        return vals, updated_labels

    def action_apply_to_partner(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("Link an Odoo contact before applying enrichment data."))
        if self.state != "done":
            raise UserError(_("Run enrichment successfully before applying data to the contact."))

        partner = self.partner_id
        vals, updated_labels = self._build_partner_update_vals(partner)

        if not vals:
            raise UserError(
                _(
                    "Nothing was updated on %(partner)s. The contact already has values "
                    "in the enriched fields (for example email, website, or job title). "
                    "Enable 'Overwrite existing fields' and try again."
                )
                % {"partner": partner.display_name}
            )

        partner.write(vals)

        return {
            "type": "ir.actions.act_window",
            "name": partner.display_name,
            "res_model": "res.partner",
            "view_mode": "form",
            "res_id": partner.id,
            "target": "current",
        }
