# -*- coding: utf-8 -*-
"""Wizard for searching contacts via Apollo API.

The wizard mirrors the enrichment wizard but uses the ``/contacts/search``
endpoint instead of ``/people/match``. It collects a few optional search
fields, builds the query parameters, calls the API and stores the raw
JSON response (truncated to 50 KB) for the user to inspect.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
import json


class ApolloContactSearch(models.TransientModel):
    _name = "apollo.contact.search"
    _description = "Apollo Contact Search"

    instance_id = fields.Many2one(
        "apollo.instance",
        string="Apollo Instance",
        required=True,
        default=lambda self: self.env["apollo.instance"].get_company_instance(),
    )
    # Search criteria – optional, but at least one must be provided.
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

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("done", "Results"),
            ("no_match", "No Match"),
            ("error", "Error"),
        ],
        default="draft",
        readonly=True,
    )
    result_message = fields.Char(string="Result", readonly=True)
    searched_at = fields.Datetime(string="Searched On", readonly=True)
    response_json = fields.Text(string="Raw Response", readonly=True)

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def _has_any_search_input(self):
        self.ensure_one()
        return any(
            (
                self.first_name,
                self.last_name,
                self.name,
                self.email,
                self.organization_name,
                self.domain,
                self.linkedin_url,
            )
        )

    def _prepare_search_params(self):
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
        return params

    def action_search(self):
        self.ensure_one()
        if not self.instance_id:
            raise UserError(_("Select an Apollo instance."))
        if not self._has_any_search_input():
            raise ValidationError(_("Provide at least one search field."))
        try:
            response = self.instance_id.search_contacts(self._prepare_search_params())
            # Apollo returns a list under "contacts" – we just store the raw JSON.
            contacts = response.get("contacts") or []
            if not contacts:
                self.write({
                    "state": "no_match",
                    "result_message": _("No contacts matched your criteria."),
                    "searched_at": fields.Datetime.now(),
                    "response_json": json.dumps(response, indent=2)[:50000],
                })
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
            # success – store response and show a simple notification.
            self.write({
                "state": "done",
                "result_message": _("Found %d contacts.") % len(contacts),
                "searched_at": fields.Datetime.now(),
                "response_json": json.dumps(response, indent=2)[:50000],
            })
            return {
                "type": "ir.actions.act_window",
                "res_model": "apollo.contact.search",
                "view_mode": "form",
                "res_id": self.id,
                "target": "new",
            }
        }
