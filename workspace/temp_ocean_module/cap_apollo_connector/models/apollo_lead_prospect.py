# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ApolloLeadProspect(models.TransientModel):
    _name = "apollo.lead.prospect"
    _description = "Apollo Lead Prospecting"

    instance_id = fields.Many2one(
        "apollo.instance",
        string="Apollo Instance",
        required=True,
        default=lambda self: self.env["apollo.instance"].get_company_instance(),
    )
    person_titles = fields.Char(
        string="Job Titles",
        help="Comma-separated titles, e.g. CEO, Sales Director",
    )
    person_locations = fields.Char(
        string="Person Locations",
        help='Comma-separated locations, e.g. "California, US", "Paris, France"',
    )
    organization_locations = fields.Char(
        string="Company HQ Locations",
        help="Comma-separated company headquarters locations.",
    )
    organization_domains = fields.Char(
        string="Company Domains",
        help="Comma-separated domains without www, e.g. apollo.io, microsoft.com",
    )
    person_seniorities = fields.Char(
        string="Seniorities",
        help="Comma-separated values such as director, manager, c_suite",
    )
    per_page = fields.Integer(string="Results Per Page", default=25)
    page = fields.Integer(string="Page", default=1)
    total_entries = fields.Integer(string="Total Results", readonly=True)
    result_message = fields.Char(string="Status", readonly=True)

    reveal_personal_emails = fields.Boolean(string="Reveal Personal Emails")
    reveal_phone_number = fields.Boolean(string="Reveal Phone Numbers")

    line_ids = fields.One2many(
        "apollo.lead.prospect.line",
        "prospect_id",
        string="Prospects",
    )

    @staticmethod
    def _split_csv(value):
        return [item.strip() for item in (value or "").split(",") if item.strip()]

    def _prepare_search_payload(self):
        self.ensure_one()
        payload = {
            "per_page": min(max(self.per_page or 25, 1), 100),
            "page": max(self.page or 1, 1),
        }
        titles = self._split_csv(self.person_titles)
        if titles:
            payload["person_titles"] = titles
        locations = self._split_csv(self.person_locations)
        if locations:
            payload["person_locations"] = locations
        org_locations = self._split_csv(self.organization_locations)
        if org_locations:
            payload["organization_locations"] = org_locations
        domains = [
            domain.lower().replace("www.", "")
            for domain in self._split_csv(self.organization_domains)
        ]
        if domains:
            payload["q_organization_domains_list"] = domains
        seniorities = self._split_csv(self.person_seniorities)
        if seniorities:
            payload["person_seniorities"] = seniorities
        if not any(
            key in payload
            for key in (
                "person_titles",
                "person_locations",
                "organization_locations",
                "q_organization_domains_list",
                "person_seniorities",
            )
        ):
            raise ValidationError(
                _("Add at least one search filter (job title, location, domain, or seniority).")
            )
        return payload

    def action_search_prospects(self):
        self.ensure_one()
        if not self.instance_id:
            raise UserError(_("Select an Apollo instance."))

        response = self.instance_id.search_people(self._prepare_search_payload())
        people = response.get("people") or []
        total_entries = response.get("total_entries") or len(people)

        self.line_ids.unlink()
        Lead = self.env["crm.lead"]
        lines = []
        for person in people:
            apollo_id = person.get("id")
            if not apollo_id:
                continue
            organization = person.get("organization") or {}
            existing_lead = Lead.search([("apollo_person_id", "=", apollo_id)], limit=1)
            lines.append(
                (
                    0,
                    0,
                    {
                        "apollo_person_id": apollo_id,
                        "first_name": person.get("first_name"),
                        "last_name_hint": person.get("last_name_obfuscated"),
                        "title": person.get("title"),
                        "organization_name": organization.get("name"),
                        "has_email": person.get("has_email"),
                        "has_direct_phone": person.get("has_direct_phone"),
                        "selected": not existing_lead,
                        "state": "existing_lead" if existing_lead else "search",
                        "existing_lead_id": existing_lead.id if existing_lead else False,
                    },
                )
            )

        message = _(
            "Found %(total)s prospects in Apollo. Showing %(shown)s on this page."
        ) % {"total": total_entries, "shown": len(lines)}
        if not lines:
            message = _("No prospects matched your search filters.")

        self.write({"total_entries": total_entries, "result_message": message, "line_ids": lines})
        return {
            "type": "ir.actions.act_window",
            "res_model": "apollo.lead.prospect",
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }

    def _bulk_enrich_options(self):
        self.ensure_one()
        options = {}
        if self.reveal_personal_emails:
            options["reveal_personal_emails"] = True
        if self.reveal_phone_number:
            options["reveal_phone_number"] = True
        return options

    def _enrich_selected_lines(self):
        self.ensure_one()
        lines = self.line_ids.filtered(lambda line: line.selected and line.state in ("search", "error"))
        if not lines:
            raise UserError(_("Select prospects that have not been enriched yet."))

        options = self._bulk_enrich_options()
        enriched_count = 0
        error_count = 0
        for index in range(0, len(lines), 10):
            batch = lines[index : index + 10]
            response = self.instance_id.bulk_enrich_people(
                batch.mapped("apollo_person_id"),
                params=options,
            )
            matches = {match.get("id"): match for match in response.get("matches") or [] if match.get("id")}
            for line in batch:
                match = matches.get(line.apollo_person_id)
                if match:
                    line._apply_enrichment_match(match)
                    enriched_count += 1
                else:
                    line.write(
                        {
                            "state": "error",
                            "error_message": _("Apollo did not return enrichment data for this person."),
                        }
                    )
                    error_count += 1

        message = _("%(count)s prospect(s) enriched.") % {"count": enriched_count}
        if error_count:
            message = "%s %s" % (
                message,
                _("%(count)s could not be enriched.") % {"count": error_count},
            )
        self.result_message = message
        return enriched_count, error_count

    def action_enrich_selected(self):
        self.ensure_one()
        self._enrich_selected_lines()
        return {
            "type": "ir.actions.act_window",
            "res_model": "apollo.lead.prospect",
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }

    def action_create_crm_leads(self):
        self.ensure_one()
        lines = self.line_ids.filtered(lambda line: line.selected and line.state == "enriched")
        if not lines:
            raise UserError(
                _("Select enriched prospects first. Use Enrich Selected before creating CRM leads.")
            )

        created_leads = self.env["crm.lead"]
        for line in lines:
            created_leads |= line.action_create_crm_lead()

        if len(created_leads) == 1:
            return {
                "type": "ir.actions.act_window",
                "name": _("CRM Lead"),
                "res_model": "crm.lead",
                "view_mode": "form",
                "res_id": created_leads.id,
                "target": "current",
            }
        return {
            "type": "ir.actions.act_window",
            "name": _("CRM Leads"),
            "res_model": "crm.lead",
            "view_mode": "list,form",
            "domain": [("id", "in", created_leads.ids)],
            "target": "current",
        }

    def action_enrich_and_create_leads(self):
        self.ensure_one()
        self._enrich_selected_lines()
        return self.action_create_crm_leads()


class ApolloLeadProspectLine(models.TransientModel):
    _name = "apollo.lead.prospect.line"
    _description = "Apollo Lead Prospect Line"
    _order = "id"

    prospect_id = fields.Many2one(
        "apollo.lead.prospect",
        required=True,
        ondelete="cascade",
    )
    selected = fields.Boolean(string="Select", default=True)
    state = fields.Selection(
        [
            ("search", "Found"),
            ("enriched", "Enriched"),
            ("lead_created", "Lead Created"),
            ("existing_lead", "Already in Odoo"),
            ("error", "Error"),
        ],
        default="search",
        readonly=True,
    )
    error_message = fields.Char(readonly=True)
    apollo_person_id = fields.Char(string="Apollo Person ID", readonly=True)
    first_name = fields.Char(readonly=True)
    last_name_hint = fields.Char(string="Last Name (preview)", readonly=True)
    title = fields.Char(readonly=True)
    organization_name = fields.Char(readonly=True)
    has_email = fields.Boolean(readonly=True)
    has_direct_phone = fields.Boolean(readonly=True)

    enriched_first_name = fields.Char(readonly=True)
    enriched_last_name = fields.Char(readonly=True)
    enriched_email = fields.Char(readonly=True)
    enriched_phone = fields.Char(readonly=True)
    enriched_title = fields.Char(readonly=True)
    enriched_organization_name = fields.Char(readonly=True)
    enriched_organization_domain = fields.Char(readonly=True)
    enriched_linkedin_url = fields.Char(readonly=True)
    enriched_city = fields.Char(readonly=True)
    enriched_state = fields.Char(readonly=True)
    enriched_country = fields.Char(readonly=True)
    email_status = fields.Char(readonly=True)

    existing_lead_id = fields.Many2one("crm.lead", readonly=True)
    crm_lead_id = fields.Many2one("crm.lead", readonly=True)
    display_name = fields.Char(compute="_compute_display_name")

    @api.depends("first_name", "last_name_hint", "enriched_first_name", "enriched_last_name", "organization_name")
    def _compute_display_name(self):
        for line in self:
            first = line.enriched_first_name or line.first_name or ""
            last = line.enriched_last_name or (line.last_name_hint or "").replace("*", "")
            name = " ".join(part for part in (first, last) if part)
            if not name:
                name = line.organization_name or line.apollo_person_id
            line.display_name = name or _("Prospect")

    @staticmethod
    def _phone_from_match(match):
        if match.get("sanitized_phone"):
            return match["sanitized_phone"]
        phone_numbers = match.get("phone_numbers") or []
        if phone_numbers:
            return phone_numbers[0].get("sanitized_number") or phone_numbers[0].get("raw_number")
        organization = match.get("organization") or {}
        primary_phone = organization.get("primary_phone") or {}
        if isinstance(primary_phone, dict):
            return primary_phone.get("sanitized_number") or primary_phone.get("number")
        return False

    def _apply_enrichment_match(self, match):
        self.ensure_one()
        organization = match.get("organization") or {}
        self.write(
            {
                "state": "enriched",
                "error_message": False,
                "enriched_first_name": match.get("first_name"),
                "enriched_last_name": match.get("last_name"),
                "enriched_email": match.get("email"),
                "enriched_phone": self._phone_from_match(match),
                "enriched_title": match.get("title"),
                "enriched_organization_name": organization.get("name") or match.get("organization_name"),
                "enriched_organization_domain": organization.get("primary_domain"),
                "enriched_linkedin_url": match.get("linkedin_url"),
                "enriched_city": match.get("city"),
                "enriched_state": match.get("state"),
                "enriched_country": match.get("country"),
                "email_status": match.get("email_status"),
            }
        )

    def _find_country_id(self, country_name):
        if not country_name:
            return False
        Country = self.env["res.country"]
        country = Country.search([("name", "=ilike", country_name.strip())], limit=1)
        if not country:
            country = Country.search([("code", "=ilike", country_name.strip())], limit=1)
        return country.id if country else False

    def _build_contact_name(self):
        self.ensure_one()
        first = self.enriched_first_name or self.first_name or ""
        last = self.enriched_last_name or ""
        return " ".join(part for part in (first, last) if part).strip()

    def _build_lead_name(self, contact_name):
        self.ensure_one()
        company = self.enriched_organization_name or self.organization_name
        if contact_name and company:
            return "%s - %s" % (contact_name, company)
        return contact_name or company or _("Apollo Lead")

    def _build_description(self):
        self.ensure_one()
        parts = []
        if self.apollo_person_id:
            parts.append("Apollo Person ID: %s" % self.apollo_person_id)
        if self.enriched_linkedin_url:
            parts.append("LinkedIn: %s" % self.enriched_linkedin_url)
        if self.email_status:
            parts.append("Email status: %s" % self.email_status)
        if self.enriched_organization_domain:
            parts.append("Company domain: %s" % self.enriched_organization_domain)
        return "\n".join(parts)

    def _prepare_crm_lead_vals(self):
        self.ensure_one()
        contact_name = self._build_contact_name()
        website = (
            "https://%s" % self.enriched_organization_domain
            if self.enriched_organization_domain
            else False
        )
        country_id = self._find_country_id(self.enriched_country)
        return {
            "name": self._build_lead_name(contact_name),
            "contact_name": contact_name,
            "partner_name": self.enriched_organization_name or self.organization_name,
            "email_from": self.enriched_email,
            "phone": self.enriched_phone,
            "function": self.enriched_title or self.title,
            "description": self._build_description(),
            "type": "opportunity",
            "apollo_person_id": self.apollo_person_id,
            "city": self.enriched_city,
            "country_id": country_id,
            "website": website,
        }

    def action_create_crm_lead(self):
        self.ensure_one()
        if self.state == "lead_created" and self.crm_lead_id:
            return self.crm_lead_id
        if self.state == "existing_lead" and self.existing_lead_id:
            raise UserError(
                _("A CRM lead already exists for %(name)s.") % {"name": self.display_name}
            )
        if self.state != "enriched":
            raise UserError(_("Enrich this prospect before creating a CRM lead."))

        duplicate_domain = [("apollo_person_id", "=", self.apollo_person_id)]
        if self.enriched_email:
            duplicate_domain = ["|"] + duplicate_domain + [("email_from", "=", self.enriched_email)]
        duplicate = self.env["crm.lead"].search(duplicate_domain, limit=1)
        if duplicate:
            self.write(
                {
                    "state": "existing_lead",
                    "existing_lead_id": duplicate.id,
                    "selected": False,
                }
            )
            return duplicate

        lead = self.env["crm.lead"].create(self._prepare_crm_lead_vals())
        self.write({"state": "lead_created", "crm_lead_id": lead.id, "selected": False})
        return lead

    def action_open_crm_lead(self):
        self.ensure_one()
        lead = self.crm_lead_id or self.existing_lead_id
        if not lead:
            raise UserError(_("No CRM lead is linked to this prospect yet."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "crm.lead",
            "view_mode": "form",
            "res_id": lead.id,
            "target": "current",
        }
