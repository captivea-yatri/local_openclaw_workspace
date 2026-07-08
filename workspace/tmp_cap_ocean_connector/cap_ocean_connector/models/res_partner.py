# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    ocean_person_id = fields.Char(
        string="Ocean Person ID",
        copy=False,
        help="Ocean.io person identifier from the last enrichment.",
    )

    def action_ocean_enrich_person(self):
        self.ensure_one()
        if not self.env["ocean.instance"].get_company_instance(self.company_id):
            raise UserError(
                _(
                    "No active Ocean.io instance is configured for company %(company)s."
                )
                % {"company": self.company_id.display_name}
            )
        return {
            "name": _("Ocean.io People Lookup"),
            "type": "ir.actions.act_window",
            "res_model": "ocean.people.enrichment",
            "view_mode": "form",
            "target": "new",
            "context": {"default_partner_id": self.id},
        }

    def action_ocean_enrich_company(self):
        self.ensure_one()
        if not self.env["ocean.instance"].get_company_instance(self.company_id):
            raise UserError(
                _(
                    "No active Ocean.io instance is configured for company %(company)s."
                )
                % {"company": self.company_id.display_name}
            )
        return {
            "name": _("Ocean.io Company Enrichment"),
            "type": "ir.actions.act_window",
            "res_model": "ocean.company.enrichment",
            "view_mode": "form",
            "target": "new",
            "context": {"default_partner_id": self.id},
        }
