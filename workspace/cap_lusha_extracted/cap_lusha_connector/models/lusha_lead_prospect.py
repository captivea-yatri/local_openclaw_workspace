# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class LushaLeadProspect(models.TransientModel):
    _name = "lusha.lead.prospect"
    _description = "Lusha Lead Prospecting"

    instance_id = fields.Many2one(
        "lusha.instance",
        string="Lusha Instance",
        required=True,
        default=lambda self: self.env["lusha.instance"].get_company_instance(),
    )
    job_titles = fields.Char(
        string="Job Titles",
        help='Comma-separated titles, e.g. "VP Sales, Director of Sales"',
    )
    departments = fields.Char(
        string="Departments",
        help='Comma-separated departments, e.g. "Sales, Engineering"',
    )
    countries = fields.Char(
        string="Countries",
        help='Comma-separated ISO country codes, e.g. "US, CA, GB"',
    )
    company_domains = fields.Char(
        string="Company Domains",
        help="Comma-separated target account domains.",
    )
    page = fields.Integer(string="Page", default=1)
    page_size = fields.Integer(string="Results Per Page", default=25)
    total_entries = fields.Integer(string="Total Results", readonly=True)
    result_message = fields.Char(string="Status", readonly=True)

    reveal_emails = fields.Boolean(string="Reveal Emails", default=True)
    reveal_phones = fields.Boolean(string="Reveal Phones")

    line_ids = fields.One2many(
        "lusha.lead.prospect.line",
        "prospect_id",
        string="Prospects",
    )

    @staticmethod
    def _split_csv(value):
        return [item.strip() for item in (value or "").split(",") if item.strip()]

    def _prepare_search_payload(self):
        self.ensure_one()
        include = {}
        job_titles = self._split_csv(self.job_titles)
        if job_titles:
            include["jobTitles"] = job_titles
        departments = self._split_csv(self.departments)
        if departments:
            include["departments"] = departments
        countries = self._split_csv(self.countries)
        if countries:
            include["countries"] = countries

        company_include = {}
        domains = [
            self.env["lusha.instance"].normalize_domain(d)
            for d in self._split_csv(self.company_domains)
        ]
        if domains:
            company_include["domains"] = domains

        if not include and not company_include:
            raise ValidationError(
                _(
                    "Add at least one search filter (job title, department, "
                    "country, or company domain)."
                )
            )

        filters = {}
        if include:
            filters["contacts"] = {"include": include}
        if company_include:
            filters["companies"] = {"include": company_include}

        return {
            "pagination": {
                "page": max(self.page or 1, 1),
                "size": min(max(self.page_size or 25, 1), 50),
            },
            "filters": filters,
        }

    def action_search_prospects(self):
        self.ensure_one()
        if not self.instance_id:
            raise UserError(_("Select a Lusha instance."))

        response = self.instance_id.prospect_contacts(self._prepare_search_payload())
        contacts = [
            item
            for item in (response.get("results") or [])
            if item.get("id") and not item.get("error")
        ]
        pagination = response.get("pagination") or {}
        total_entries = pagination.get("total") or len(contacts)

        self.line_ids.unlink()
        Lead = self.env["crm.lead"]
        Instance = self.env["lusha.instance"]
        lines = []
        for contact in contacts:
            lusha_id = contact.get("id")
            existing_lead = Lead.search([("lusha_contact_id", "=", lusha_id)], limit=1)
            company = contact.get("company") or {}
            job = contact.get("jobTitle") or {}
            can_reveal = contact.get("canReveal") or []
            has_email = any(
                item.get("field") == "emails" for item in can_reveal if isinstance(item, dict)
            )
            has_phone = any(
                item.get("field") == "phones" for item in can_reveal if isinstance(item, dict)
            )
            lines.append(
                (
                    0,
                    0,
                    {
                        "lusha_contact_id": lusha_id,
                        "first_name": contact.get("firstName"),
                        "last_name": contact.get("lastName"),
                        "title": job.get("title") if isinstance(job, dict) else False,
                        "company_name": company.get("name") if isinstance(company, dict) else False,
                        "company_domain": Instance.extract_company_domain(contact),
                        "linkedin_url": Instance.extract_linkedin_url(contact),
                        "has_email": has_email,
                        "has_phone": has_phone,
                        "selected": not existing_lead,
                        "state": "existing_lead" if existing_lead else "search",
                        "existing_lead_id": existing_lead.id if existing_lead else False,
                    },
                )
            )

        message = _(
            "Found %(total)s prospects in Lusha. Showing %(shown)s on this page."
        ) % {"total": total_entries, "shown": len(lines)}
        if not lines:
            message = _("No prospects matched your search filters.")

        self.write({"total_entries": total_entries, "result_message": message, "line_ids": lines})
        return {
            "type": "ir.actions.act_window",
            "res_model": "lusha.lead.prospect",
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }

    def _enrich_selected_lines(self):
        self.ensure_one()
        lines = self.line_ids.filtered(
            lambda line: line.selected and line.state in ("search", "error")
        )
        if not lines:
            raise UserError(_("Select prospects that have not been enriched yet."))

        reveal = []
        if self.reveal_emails:
            reveal.append("emails")
        if self.reveal_phones:
            reveal.append("phones")
        if not reveal:
            reveal = ["emails"]

        enriched_count = 0
        error_count = 0
        for index in range(0, len(lines), 100):
            batch = lines[index : index + 100]
            payload = {
                "ids": batch.mapped("lusha_contact_id"),
                "reveal": reveal,
            }
            response = self.instance_id.enrich_contacts(payload)
            matches = {
                item.get("id"): item
                for item in (response.get("results") or [])
                if item.get("id") and not item.get("error")
            }
            for line in batch:
                match = matches.get(line.lusha_contact_id)
                if match:
                    line._apply_enrichment_match(match)
                    enriched_count += 1
                else:
                    line.write(
                        {
                            "state": "error",
                            "error_message": _("Lusha did not return enrichment data."),
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
            "res_model": "lusha.lead.prospect",
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


class LushaLeadProspectLine(models.TransientModel):
    _name = "lusha.lead.prospect.line"
    _description = "Lusha Lead Prospect Line"
    _order = "id"

    prospect_id = fields.Many2one(
        "lusha.lead.prospect",
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
    lusha_contact_id = fields.Char(string="Lusha Contact ID", readonly=True)
    first_name = fields.Char(readonly=True)
    last_name = fields.Char(readonly=True)
    title = fields.Char(readonly=True)
    company_name = fields.Char(readonly=True)
    company_domain = fields.Char(readonly=True)
    linkedin_url = fields.Char(readonly=True)
    has_email = fields.Boolean(readonly=True)
    has_phone = fields.Boolean(readonly=True)

    enriched_email = fields.Char(readonly=True)
    enriched_phone = fields.Char(readonly=True)
    enriched_title = fields.Char(readonly=True)
    enriched_company_name = fields.Char(readonly=True)
    enriched_company_domain = fields.Char(readonly=True)
    enriched_linkedin_url = fields.Char(readonly=True)
    enriched_city = fields.Char(readonly=True)
    enriched_country = fields.Char(readonly=True)
    email_confidence = fields.Char(readonly=True)

    existing_lead_id = fields.Many2one("crm.lead", readonly=True)
    crm_lead_id = fields.Many2one("crm.lead", readonly=True)
    display_name = fields.Char(compute="_compute_display_name")

    @api.depends("first_name", "last_name", "company_name", "lusha_contact_id")
    def _compute_display_name(self):
        for line in self:
            name = " ".join(part for part in (line.first_name, line.last_name) if part)
            if not name:
                name = line.company_name or line.lusha_contact_id
            line.display_name = name or _("Prospect")

    def _apply_enrichment_match(self, match):
        self.ensure_one()
        Instance = self.env["lusha.instance"]
        email, _etype, confidence = Instance.extract_contact_email(match)
        location = match.get("location") or {}
        company = match.get("company") or {}
        self.write(
            {
                "state": "enriched",
                "error_message": False,
                "enriched_email": email,
                "email_confidence": confidence,
                "enriched_phone": Instance.extract_contact_phone(match),
                "enriched_title": Instance.extract_job_title(match) or self.title,
                "enriched_company_name": company.get("name") if isinstance(company, dict) else self.company_name,
                "enriched_company_domain": Instance.extract_company_domain(match) or self.company_domain,
                "enriched_linkedin_url": Instance.extract_linkedin_url(match) or self.linkedin_url,
                "enriched_city": location.get("city"),
                "enriched_country": location.get("country"),
            }
        )

    def _find_country_id(self, country_name):
        if not country_name:
            return False
        Country = self.env["res.country"]
        country = Country.search([("name", "=ilike", country_name.strip())], limit=1)
        return country.id if country else False

    def _build_contact_name(self):
        self.ensure_one()
        return " ".join(part for part in (self.first_name, self.last_name) if part).strip()

    def _build_lead_name(self, contact_name):
        self.ensure_one()
        company = self.enriched_company_name or self.company_name
        if contact_name and company:
            return "%s - %s" % (contact_name, company)
        return contact_name or company or _("Lusha Lead")

    def _prepare_crm_lead_vals(self):
        self.ensure_one()
        contact_name = self._build_contact_name()
        website = (
            "https://%s" % self.enriched_company_domain
            if self.enriched_company_domain
            else False
        )
        return {
            "name": self._build_lead_name(contact_name),
            "contact_name": contact_name,
            "partner_name": self.enriched_company_name or self.company_name,
            "email_from": self.enriched_email,
            "phone": self.enriched_phone,
            "function": self.enriched_title or self.title,
            "type": "opportunity",
            "lusha_contact_id": self.lusha_contact_id,
            "city": self.enriched_city,
            "country_id": self._find_country_id(self.enriched_country),
            "website": website,
            "description": "\n".join(
                part
                for part in (
                    "Lusha Contact ID: %s" % self.lusha_contact_id if self.lusha_contact_id else False,
                    "LinkedIn: %s" % self.enriched_linkedin_url if self.enriched_linkedin_url else False,
                    "Email confidence: %s" % self.email_confidence if self.email_confidence else False,
                )
                if part
            ),
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

        duplicate_domain = [("lusha_contact_id", "=", self.lusha_contact_id)]
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
        Tag = self.env["crm.tag"]
        lusha_tag = Tag.search([("name", "=", "Lusha")], limit=1)
        if not lusha_tag:
          lusha_tag = Tag.create({"name": "Lusha"})

        # Assign tag to lead
        lead.tag_ids = [(4, lusha_tag.id)]
        self.write({"state": "lead_created", "crm_lead_id": lead.id, "selected": False})
        return lead
