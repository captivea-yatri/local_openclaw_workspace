# -*- coding: utf-8 -*-
import json
from urllib.parse import urlparse

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class OceanPeopleEnrichment(models.TransientModel):
    _name = "ocean.people.enrichment"
    _description = "Ocean.io People Lookup"

    instance_id = fields.Many2one(
        "ocean.instance",
        string="Ocean.io Instance",
        required=True,
        default=lambda self: self.env["ocean.instance"].get_company_instance(),
    )
    partner_id = fields.Many2one("res.partner", string="Odoo Contact")
    lookup_method = fields.Selection(
        [
            ("auto", "Automatic (recommended)"),
            ("lookup", "Fast lookup (LinkedIn / Ocean ID only)"),
            ("enrich", "Full enrich (email, LinkedIn, name + company)"),
            ("search", "People search (name + company, multiple candidates)"),
        ],
        string="Method",
        default="auto",
        required=True,
        help="Automatic picks the best endpoint. Use People search when you only "
        "have a name and company and enrich returns insufficient data.",
    )

    ocean_person_id = fields.Char(string="Ocean Person ID")
    linkedin_url = fields.Char(string="LinkedIn URL")
    linkedin_handle = fields.Char(
        string="LinkedIn Handle",
        help="Example: jane-doe-123 (from linkedin.com/in/jane-doe-123)",
    )
    email = fields.Char(string="Email")
    phone = fields.Char(string="Phone")
    name = fields.Char(string="Full Name")
    first_name = fields.Char(string="First Name")
    last_name = fields.Char(string="Last Name")
    job_title = fields.Char(string="Job Title")
    country = fields.Char(
        string="Country Code",
        help="Alpha-2 ISO country code, e.g. us, de, fr",
    )
    company_domain = fields.Char(
        string="Company Domain",
        help="Example: company.com (without www.)",
    )
    company_name = fields.Char(string="Company Name")

    reveal_emails = fields.Boolean(
        string="Reveal Emails",
        help="Request verified email reveal (async webhook, consumes email credits).",
    )
    reveal_phones = fields.Boolean(
        string="Reveal Phones",
        help="Request verified phone reveal (async webhook, consumes phone credits).",
    )
    apply_overwrite = fields.Boolean(
        string="Overwrite Existing Fields",
        help="When enabled, Ocean.io values replace existing contact fields.",
    )

    state = fields.Selection(
        [("draft", "Draft"), ("done", "Enriched"), ("no_match", "No Match"), ("error", "Error")],
        default="draft",
        readonly=True,
    )
    result_message = fields.Char(string="Result", readonly=True)
    enriched_at = fields.Datetime(string="Enriched On", readonly=True)

    enriched_ocean_id = fields.Char(string="Ocean Person ID", readonly=True)
    enriched_name = fields.Char(string="Name", readonly=True)
    enriched_first_name = fields.Char(string="First Name", readonly=True)
    enriched_last_name = fields.Char(string="Last Name", readonly=True)
    enriched_email = fields.Char(string="Email", readonly=True)
    enriched_title = fields.Char(string="Job Title", readonly=True)
    enriched_linkedin_url = fields.Char(string="LinkedIn", readonly=True)
    enriched_domain = fields.Char(string="Company Domain", readonly=True)
    enriched_company_name = fields.Char(string="Company", readonly=True)
    enriched_phone = fields.Char(string="Phone", readonly=True)
    enriched_country = fields.Char(string="Country", readonly=True)
    enriched_location = fields.Char(string="Location", readonly=True)
    email_status = fields.Char(string="Email Status", readonly=True)
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
            vals.setdefault("ocean_person_id", partner.ocean_person_id)
            vals.setdefault("email", partner.email)
            vals.setdefault("phone", partner.phone or getattr(partner, "mobile", False))
            vals.setdefault("job_title", partner.function)
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
                vals.setdefault("name", partner.name)

            domain = self._domain_from_website(partner.website)
            if not domain:
                domain = self._domain_from_email(partner.email)
            vals.setdefault("company_domain", domain)

            if partner.country_id:
                vals.setdefault("country", partner.country_id.code.lower())

            linkedin = getattr(partner, "linkedin_url", None) or getattr(partner, "linkedin", None)
            if linkedin:
                vals.setdefault("linkedin_url", linkedin)
                vals.setdefault(
                    "linkedin_handle",
                    self.env["ocean.instance"].linkedin_handle_from_url(linkedin),
                )
        return vals

    @api.onchange("linkedin_url")
    def _onchange_linkedin_url(self):
        if self.linkedin_url:
            self.linkedin_handle = self.env["ocean.instance"].linkedin_handle_from_url(
                self.linkedin_url
            )

    def _get_linkedin_handle(self):
        self.ensure_one()
        handle = (self.linkedin_handle or "").strip()
        if not handle and self.linkedin_url:
            handle = self.env["ocean.instance"].linkedin_handle_from_url(self.linkedin_url)
        return handle or False

    def _resolve_lookup_method(self):
        self.ensure_one()
        if self.lookup_method != "auto":
            return self.lookup_method
        if self.reveal_emails or self.reveal_phones:
            return "enrich"

        has_ocean_id = bool((self.ocean_person_id or "").strip())
        has_linkedin = bool(self._get_linkedin_handle())
        has_email = bool((self.email or "").strip())
        has_name = bool((self.name or "").strip()) or bool(
            (self.first_name or "").strip() and (self.last_name or "").strip()
        )
        has_company = bool((self.company_domain or "").strip()) or bool(
            (self.company_name or "").strip()
        )

        if has_ocean_id or has_linkedin:
            if not has_email and not has_name and not has_company and not (self.job_title or "").strip():
                return "lookup"
        if has_name and has_company and not has_ocean_id and not has_linkedin and not has_email:
            return "search"
        if has_ocean_id or has_linkedin:
            return "lookup"
        return "enrich"

    @staticmethod
    def _is_insufficient_match_error(error_message):
        message = (error_message or "").lower()
        return "insufficient" in message and "high confidence" in message

    def _get_target_name(self):
        self.ensure_one()
        if (self.name or "").strip():
            return self.name.strip()
        if (self.first_name or "").strip() and (self.last_name or "").strip():
            return "%s %s" % (self.first_name.strip(), self.last_name.strip())
        return ""

    def _prepare_search_payload(self):
        self.ensure_one()
        payload = {"size": 10, "peoplePerCompany": 5}
        people_filters = {}

        target_name = self._get_target_name()
        if target_name:
            people_filters["names"] = [target_name]
        if self.job_title:
            people_filters["jobTitleKeywords"] = {"anyOf": [self.job_title.strip()]}
        if self.country:
            people_filters["countries"] = [self.country.strip().lower()]

        handle = self._get_linkedin_handle()
        if handle:
            people_filters["includeLinkedinHandles"] = [handle]
        if (self.ocean_person_id or "").strip():
            people_filters["includePeopleIds"] = [self.ocean_person_id.strip()]
        if people_filters:
            payload["peopleFilters"] = people_filters

        companies_filters = {}
        if self.company_domain:
            companies_filters["includeDomains"] = [
                self.company_domain.strip().lower().replace("www.", "")
            ]
        if companies_filters:
            payload["companiesFilters"] = companies_filters
        return payload

    def _pick_best_person_match(self, people):
        self.ensure_one()
        if not people:
            return None
        if len(people) == 1:
            return people[0]

        target_name = self._get_target_name().lower()
        target_title = (self.job_title or "").strip().lower()
        target_domain = (self.company_domain or "").strip().lower().replace("www.", "")

        def _score(person):
            score = 0
            person_name = (person.get("name") or "").strip().lower()
            if target_name and person_name == target_name:
                score += 100
            elif target_name and target_name in person_name:
                score += 60
            elif target_name:
                first, last = self.env["ocean.instance"].split_person_name(person)
                candidate = "%s %s" % (first, last)
                if candidate.strip().lower() == target_name:
                    score += 90

            title = (person.get("jobTitle") or person.get("jobTitleEnglish") or "").lower()
            if target_title and target_title in title:
                score += 20

            domain = (person.get("domain") or "").lower()
            if target_domain and domain == target_domain:
                score += 15
            return score

        return max(people, key=_score)

    def _run_person_search(self):
        self.ensure_one()
        payload = self._prepare_search_payload()
        if not payload.get("peopleFilters") and not payload.get("companiesFilters"):
            raise UserError(
                _(
                    "People search requires at least a name and company domain, "
                    "or another people/company filter."
                )
            )
        response = self.instance_id.search_people(payload)
        people = response.get("people") or []
        person = self._pick_best_person_match(people)
        if not person:
            return None, response
        return person, response

    def _validate_search_inputs(self):
        self.ensure_one()
        method = self._resolve_lookup_method()
        has_ocean_id = bool((self.ocean_person_id or "").strip())
        has_linkedin = bool(self._get_linkedin_handle() or (self.linkedin_url or "").strip())
        has_email = bool((self.email or "").strip())
        has_phone = bool((self.phone or "").strip())
        has_name = bool((self.name or "").strip())
        has_first_last = bool(self.first_name and self.last_name)
        has_company_domain = bool((self.company_domain or "").strip())
        has_company_name = bool((self.company_name or "").strip())

        if method == "lookup":
            if has_ocean_id or has_linkedin:
                return
            raise ValidationError(
                _(
                    "Fast lookup requires an Ocean person ID or a LinkedIn URL/handle.\n"
                    "For name, email, or company-based matching, switch Method to "
                    "'Full enrich', 'People search', or 'Automatic'."
                )
            )

        if method == "search":
            has_name = bool(self._get_target_name())
            if has_name and (has_company_domain or has_company_name):
                return
            if has_ocean_id or has_linkedin:
                return
            raise ValidationError(
                _(
                    "People search works best with a name and company domain.\n"
                    "Example: First/Last name + company.com"
                )
            )

        if has_ocean_id or has_linkedin or has_email:
            return
        if has_name and (has_company_domain or has_company_name):
            return
        if has_first_last and (has_company_domain or has_company_name or has_email):
            return
        if has_first_last and has_phone:
            return
        raise ValidationError(
            _(
                "Provide enough data for Ocean.io to find a person:\n"
                "- Ocean person ID, LinkedIn URL/handle, or email\n"
                "- OR full name + company domain or company name\n"
                "- OR first name + last name + company domain, company name, or email"
            )
        )

    def _prepare_lookup_params(self):
        self.ensure_one()
        ocean_ids = []
        linkedin_handles = []
        if self.ocean_person_id:
            ocean_ids.append(self.ocean_person_id.strip())
        handle = self._get_linkedin_handle()
        if handle:
            linkedin_handles.append(handle)
        return linkedin_handles, ocean_ids

    def _prepare_enrich_payload(self):
        self.ensure_one()
        OceanInstance = self.env["ocean.instance"]
        person = {}
        if self.ocean_person_id:
            person["id"] = self.ocean_person_id.strip()
        linkedin = OceanInstance.normalize_linkedin_for_enrich(
            self.linkedin_url, self.linkedin_handle
        )
        if linkedin:
            person["linkedin"] = linkedin
        if self.email:
            person["email"] = self.email.strip()
        if self.phone:
            person["phone"] = self.phone.strip()
        if self.name:
            person["name"] = self.name.strip()
        if self.first_name:
            person["firstName"] = self.first_name.strip()
        if self.last_name:
            person["lastName"] = self.last_name.strip()
        if self.job_title:
            person["jobTitle"] = self.job_title.strip()
        if self.country:
            person["country"] = self.country.strip().lower()

        company = {}
        if self.company_domain:
            company["domain"] = self.company_domain.strip().lower().replace("www.", "")
        if self.company_name:
            company["name"] = self.company_name.strip()
        return person, company or None

    def _apply_person_data(self, person, response=None, result_message=None):
        self.ensure_one()
        if not person or not person.get("id"):
            self.write(
                {
                    "state": "no_match",
                    "result_message": _(
                        "Ocean.io did not find a matching person. "
                        "Add LinkedIn, email, or name + company domain and try again."
                    ),
                    "enriched_at": fields.Datetime.now(),
                    "response_json": json.dumps(response or person or {}, indent=2)[:50000],
                }
            )
            return False

        OceanInstance = self.env["ocean.instance"]
        first_name, last_name = OceanInstance.split_person_name(person)
        message = result_message or _("Person enriched successfully.")
        if self.reveal_emails or self.reveal_phones:
            parts = []
            if self.reveal_emails:
                parts.append(_("email reveal"))
            if self.reveal_phones:
                parts.append(_("phone reveal"))
            message = _(
                "Person enriched. %(parts)s may arrive asynchronously on your webhook URL."
            ) % {"parts": " / ".join(parts)}

        self.write(
            {
                "state": "done",
                "result_message": message,
                "enriched_at": fields.Datetime.now(),
                "enriched_ocean_id": person.get("id"),
                "enriched_name": person.get("name"),
                "enriched_first_name": first_name,
                "enriched_last_name": last_name,
                "enriched_email": OceanInstance.extract_person_email(person),
                "enriched_title": person.get("jobTitle") or person.get("jobTitleEnglish"),
                "enriched_linkedin_url": person.get("linkedinUrl"),
                "enriched_domain": person.get("domain"),
                "enriched_company_name": OceanInstance.extract_company_name(person),
                "enriched_phone": OceanInstance.extract_person_phone(person),
                "enriched_country": person.get("country"),
                "enriched_location": person.get("location"),
                "email_status": OceanInstance.extract_person_email_status(person),
                "response_json": json.dumps(response or person, indent=2)[:50000],
            }
        )
        if self.partner_id and person.get("id"):
            if not self.partner_id.ocean_person_id:
                self.partner_id.sudo().write({"ocean_person_id": person.get("id")})
            if self.reveal_emails or self.reveal_phones:
                target_types = []
                if self.reveal_emails:
                    target_types.append("email")
                if self.reveal_phones:
                    target_types.append("phone")
                self.instance_id.register_webhook_targets(
                    [person.get("id")],
                    partner_id=self.partner_id.id,
                    target_types=target_types,
                )
        return True

    def action_enrich(self):
        self.ensure_one()
        if not self.instance_id:
            raise UserError(_("Select an Ocean.io instance."))
        self._validate_search_inputs()
        method = self._resolve_lookup_method()
        if self.reveal_emails or self.reveal_phones:
            if not (self.instance_id.webhook_url or "").strip():
                enabled = []
                if self.reveal_emails:
                    enabled.append(_("Reveal Emails"))
                if self.reveal_phones:
                    enabled.append(_("Reveal Phones"))
                raise UserError(
                    _(
                        "%(options)s requires a public HTTPS webhook URL.\n\n"
                        "Open Ocean.io → Configuration, set Public HTTPS URL (ngrok) or "
                        "ensure web.base.url is HTTPS, then save."
                    )
                    % {"options": " / ".join(enabled)}
                )

        reveal_sent = False
        try:
            if method == "lookup":
                linkedin_handles, ocean_ids = self._prepare_lookup_params()
                response = self.instance_id.lookup_people(
                    linkedin_handles=linkedin_handles,
                    ocean_ids=ocean_ids,
                )
                people = response.get("people") or []
                matched = self._apply_person_data(people[0] if people else {}, response)
            elif method == "search":
                person, response = self._run_person_search()
                matched = self._apply_person_data(person or {}, response)
            else:
                person_data, company_data = self._prepare_enrich_payload()
                try:
                    response = self.instance_id.enrich_person(
                        person_data,
                        company_data=company_data,
                        reveal_emails=self.reveal_emails,
                        reveal_phones=self.reveal_phones,
                        partner_id=self.partner_id.id if self.partner_id else None,
                    )
                    reveal_sent = bool(self.reveal_emails or self.reveal_phones)
                    matched = self._apply_person_data(response, response)
                except UserError as err:
                    if self._is_insufficient_match_error(str(err)):
                        person, response = self._run_person_search()
                        if person:
                            matched = self._apply_person_data(
                                person,
                                response,
                                result_message=_(
                                    "Person found via People Search after enrich could "
                                    "not make a high-confidence match."
                                ),
                            )
                        else:
                            raise UserError(
                                _(
                                    "Ocean.io could not make a high-confidence match with "
                                    "the fields provided.\n\n"
                                    "Try adding a stronger identifier:\n"
                                    "- LinkedIn URL (best after Ocean ID)\n"
                                    "- Work email\n"
                                    "- First name + last name + company domain + job title\n\n"
                                    "Or switch Method to 'People search' and ensure company "
                                    "domain is filled in."
                                )
                            ) from err
                    else:
                        raise
        except UserError as err:
            self.write(
                {
                    "state": "error",
                    "result_message": str(err)[:255],
                    "enriched_at": fields.Datetime.now(),
                }
            )
            raise

        if matched and self.enriched_ocean_id and not reveal_sent:
            partner_id = self.partner_id.id if self.partner_id else None
            if self.reveal_emails:
                self.instance_id.reveal_emails(
                    [self.enriched_ocean_id],
                    partner_id=partner_id,
                )
            if self.reveal_phones:
                self.instance_id.reveal_phones(
                    [self.enriched_ocean_id],
                    partner_id=partner_id,
                )
            if self.reveal_emails or self.reveal_phones:
                self.result_message = _(
                    "%(msg)s Reveal requested — email/phone will arrive via webhook in a few minutes."
                ) % {"msg": self.result_message or ""}

        if not matched:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Ocean.io"),
                    "message": self.result_message,
                    "type": "warning",
                    "sticky": False,
                },
            }
        return {
            "type": "ir.actions.act_window",
            "res_model": "ocean.people.enrichment",
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

    def _find_country_id(self, country_code):
        if not country_code:
            return False
        Country = self.env["res.country"]
        country = Country.search([("code", "=ilike", country_code.strip())], limit=1)
        return country.id if country else False

    def _build_partner_update_vals(self, partner):
        self.ensure_one()
        vals = {}
        if self._should_write_field(partner.email, self.enriched_email):
            vals["email"] = self.enriched_email
        if self._should_write_field(partner.function, self.enriched_title):
            vals["function"] = self.enriched_title
        if self.enriched_phone and self._should_write_field(partner.phone, self.enriched_phone):
            vals["phone"] = self.enriched_phone
        website_value = (
            "https://%s" % self.enriched_domain if self.enriched_domain else False
        )
        if self._should_write_field(partner.website, website_value):
            vals["website"] = website_value
        if hasattr(partner, "linkedin_url") and partner._fields.get("linkedin_url"):
            if self._should_write_field(partner.linkedin_url, self.enriched_linkedin_url):
                vals["linkedin_url"] = self.enriched_linkedin_url
        first = self.enriched_first_name
        last = self.enriched_last_name
        if hasattr(partner, "firstname") and partner._fields.get("firstname"):
            if first and self._should_write_field(partner.firstname, first):
                vals["firstname"] = first
            if last and self._should_write_field(partner.lastname, last):
                vals["lastname"] = last
        elif self.enriched_name and self._should_write_field(partner.name, self.enriched_name):
            vals["name"] = self.enriched_name
        country_id = self._find_country_id(self.enriched_country)
        if country_id and (self.apply_overwrite or not partner.country_id):
            vals["country_id"] = country_id
        if self.enriched_ocean_id and (
            self.apply_overwrite or not partner.ocean_person_id
        ):
            vals["ocean_person_id"] = self.enriched_ocean_id
        return vals

    def action_apply_to_partner(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("Link an Odoo contact before applying enrichment data."))
        if self.state != "done":
            raise UserError(_("Run lookup successfully before applying data to the contact."))

        partner = self.partner_id
        vals = self._build_partner_update_vals(partner)
        if not vals:
            raise UserError(
                _(
                    "Nothing was updated on %(partner)s. Enable 'Overwrite existing fields' "
                    "and try again."
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
