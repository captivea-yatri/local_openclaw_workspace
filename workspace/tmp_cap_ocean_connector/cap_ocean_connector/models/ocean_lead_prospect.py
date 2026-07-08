# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class OceanLeadProspect(models.TransientModel):
    _name = "ocean.lead.prospect"
    _description = "Ocean.io Lead Prospecting"

    instance_id = fields.Many2one(
        "ocean.instance",
        string="Ocean.io Instance",
        required=True,
        default=lambda self: self.env["ocean.instance"].get_company_instance(),
    )
    seniorities = fields.Char(
        string="Seniorities",
        help='Comma-separated values, e.g. "VP, C-Level, Director"',
    )
    departments = fields.Char(
        string="Departments",
        help='Comma-separated values, e.g. "Sales, Marketing and Advertising"',
    )
    job_title_keywords = fields.Char(
        string="Job Title Keywords",
        help='Comma-separated keywords matched with anyOf, e.g. "Sales, Revenue"',
    )
    lookalike_domains = fields.Char(
        string="Lookalike Domains",
        help="Comma-separated seed customer domains for lookalike search.",
    )
    include_domains = fields.Char(
        string="Target Domains",
        help="Comma-separated target account domains.",
    )
    company_sizes = fields.Char(
        string="Company Sizes",
        help='Comma-separated ranges, e.g. "51-200, 201-500"',
    )
    size = fields.Integer(string="Results", default=50)
    people_per_company = fields.Integer(
        string="People Per Company",
        default=1,
        help="Maximum contacts returned per company domain.",
    )
    total_entries = fields.Integer(string="Total Results", readonly=True)
    result_message = fields.Char(string="Status", readonly=True)
    reveal_emails = fields.Boolean(
        string="Reveal Emails",
        help="Request verified emails via webhook after search (consumes email credits).",
    )

    line_ids = fields.One2many(
        "ocean.lead.prospect.line",
        "prospect_id",
        string="Prospects",
    )

    @staticmethod
    def _split_csv(value):
        return [item.strip() for item in (value or "").split(",") if item.strip()]

    @staticmethod
    def _normalize_domains(value):
        return [
            domain.lower().replace("www.", "")
            for domain in OceanLeadProspect._split_csv(value)
        ]

    def _prepare_search_payload(self):
        self.ensure_one()
        payload = {
            "size": min(max(self.size or 50, 1), 200),
        }
        if self.people_per_company:
            payload["peoplePerCompany"] = max(self.people_per_company, 1)

        people_filters = {}
        seniorities = self._split_csv(self.seniorities)
        if seniorities:
            people_filters["seniorities"] = seniorities
        departments = self._split_csv(self.departments)
        if departments:
            people_filters["departments"] = departments
        keywords = self._split_csv(self.job_title_keywords)
        if keywords:
            people_filters["jobTitleKeywords"] = {"anyOf": keywords}
        if people_filters:
            payload["peopleFilters"] = people_filters

        companies_filters = {}
        lookalike_domains = self._normalize_domains(self.lookalike_domains)
        if lookalike_domains:
            companies_filters["lookalikeDomains"] = lookalike_domains
        include_domains = self._normalize_domains(self.include_domains)
        if include_domains:
            companies_filters["includeDomains"] = include_domains
        company_sizes = self._split_csv(self.company_sizes)
        if company_sizes:
            companies_filters["companySizes"] = company_sizes
        if companies_filters:
            payload["companiesFilters"] = companies_filters

        if not people_filters and not companies_filters:
            raise ValidationError(
                _(
                    "Add at least one search filter (seniority, department, "
                    "lookalike domain, or target domain)."
                )
            )
        return payload

    def action_search_prospects(self):
        self.ensure_one()
        if not self.instance_id:
            raise UserError(_("Select an Ocean.io instance."))

        response = self.instance_id.search_people(self._prepare_search_payload())
        people = response.get("people") or []
        total_entries = response.get("total") or len(people)

        self.line_ids.unlink()
        Lead = self.env["crm.lead"]
        OceanInstance = self.env["ocean.instance"]
        lines = []
        for person in people:
            ocean_id = person.get("id")
            if not ocean_id:
                continue
            first_name, last_name = OceanInstance.split_person_name(person)
            company_name = OceanInstance.extract_company_name(person)
            email = OceanInstance.extract_person_email(person)
            existing_lead = Lead.search([("ocean_person_id", "=", ocean_id)], limit=1)
            lines.append(
                (
                    0,
                    0,
                    {
                        "ocean_person_id": ocean_id,
                        "first_name": first_name,
                        "last_name": last_name,
                        "name": person.get("name"),
                        "title": person.get("jobTitle") or person.get("jobTitleEnglish"),
                        "organization_name": company_name,
                        "organization_domain": person.get("domain"),
                        "linkedin_url": person.get("linkedinUrl"),
                        "email": email,
                        "email_status": OceanInstance.extract_person_email_status(person),
                        "phone": OceanInstance.extract_person_phone(person),
                        "has_email": bool(email),
                        "selected": not existing_lead,
                        "state": "existing_lead" if existing_lead else "search",
                        "existing_lead_id": existing_lead.id if existing_lead else False,
                    },
                )
            )

        message = _(
            "Found %(total)s prospects in Ocean.io. Showing %(shown)s results."
        ) % {"total": total_entries, "shown": len(lines)}
        if not lines:
            message = _("No prospects matched your search filters.")

        self.write({"total_entries": total_entries, "result_message": message, "line_ids": lines})
        return {
            "type": "ir.actions.act_window",
            "res_model": "ocean.lead.prospect",
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }

    def action_reveal_emails_selected(self):
        self.ensure_one()
        lines = self.line_ids.filtered(
            lambda line: line.selected and line.ocean_person_id and not line.email
        )
        if not lines:
            raise UserError(_("Select prospects without email to reveal addresses."))
        person_ids = lines.mapped("ocean_person_id")
        for index in range(0, len(person_ids), 500):
            self.instance_id.reveal_emails(person_ids[index : index + 500])
        self.result_message = _(
            "Email reveal requested for %(count)s prospect(s). "
            "Results will arrive on your webhook URL."
        ) % {"count": len(person_ids)}
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Ocean.io"),
                "message": self.result_message,
                "type": "info",
                "sticky": False,
            },
        }

    def action_create_crm_leads(self):
        self.ensure_one()
        lines = self.line_ids.filtered(lambda line: line.selected and line.state == "search")
        if not lines:
            raise UserError(_("Select prospects that are not already imported as CRM leads."))

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


class OceanLeadProspectLine(models.TransientModel):
    _name = "ocean.lead.prospect.line"
    _description = "Ocean.io Lead Prospect Line"
    _order = "id"

    prospect_id = fields.Many2one(
        "ocean.lead.prospect",
        required=True,
        ondelete="cascade",
    )
    selected = fields.Boolean(string="Select", default=True)
    state = fields.Selection(
        [
            ("search", "Found"),
            ("lead_created", "Lead Created"),
            ("existing_lead", "Already in Odoo"),
            ("error", "Error"),
        ],
        default="search",
        readonly=True,
    )
    error_message = fields.Char(readonly=True)
    ocean_person_id = fields.Char(string="Ocean Person ID", readonly=True)
    name = fields.Char(readonly=True)
    first_name = fields.Char(readonly=True)
    last_name = fields.Char(readonly=True)
    title = fields.Char(readonly=True)
    organization_name = fields.Char(readonly=True)
    organization_domain = fields.Char(readonly=True)
    linkedin_url = fields.Char(readonly=True)
    email = fields.Char(readonly=True)
    phone = fields.Char(readonly=True)
    email_status = fields.Char(readonly=True)
    has_email = fields.Boolean(readonly=True)
    existing_lead_id = fields.Many2one("crm.lead", readonly=True)
    crm_lead_id = fields.Many2one("crm.lead", readonly=True)
    display_name = fields.Char(compute="_compute_display_name")

    @api.depends("first_name", "last_name", "name", "organization_name")
    def _compute_display_name(self):
        for line in self:
            name = " ".join(
                part
                for part in (line.first_name or "", line.last_name or "")
                if part
            )
            if not name:
                name = line.name or line.organization_name or line.ocean_person_id
            line.display_name = name or _("Prospect")

    def _build_contact_name(self):
        self.ensure_one()
        return " ".join(
            part for part in (self.first_name or "", self.last_name or "") if part
        ).strip() or (self.name or "")

    def _build_lead_name(self, contact_name):
        self.ensure_one()
        company = self.organization_name
        if contact_name and company:
            return "%s - %s" % (contact_name, company)
        return contact_name or company or _("Ocean.io Lead")

    def _build_description(self):
        self.ensure_one()
        parts = []
        if self.ocean_person_id:
            parts.append("Ocean Person ID: %s" % self.ocean_person_id)
        if self.linkedin_url:
            parts.append("LinkedIn: %s" % self.linkedin_url)
        if self.email_status:
            parts.append("Email status: %s" % self.email_status)
        if self.organization_domain:
            parts.append("Company domain: %s" % self.organization_domain)
        return "\n".join(parts)

    def _prepare_crm_lead_vals(self):
        self.ensure_one()
        contact_name = self._build_contact_name()
        website = (
            "https://%s" % self.organization_domain if self.organization_domain else False
        )
        return {
            "name": self._build_lead_name(contact_name),
            "contact_name": contact_name,
            "partner_name": self.organization_name,
            "email_from": self.email,
            "phone": self.phone,
            "function": self.title,
            "description": self._build_description(),
            "type": "opportunity",
            "ocean_person_id": self.ocean_person_id,
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

        duplicate_domain = [("ocean_person_id", "=", self.ocean_person_id)]
        if self.email:
            duplicate_domain = ["|"] + duplicate_domain + [("email_from", "=", self.email)]
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
