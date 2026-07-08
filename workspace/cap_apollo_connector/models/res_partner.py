# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    apollo_person_id = fields.Char(
        string="Apollo Person ID",
        copy=False,
        help="Apollo.io person identifier from the last enrichment.",
    )

    def action_apollo_enrich_person(self):
        self.ensure_one()
        if not self.env["apollo.instance"].get_company_instance(self.company_id):
            raise UserError(
                _(
                    "No active Apollo instance is configured for company %(company)s."
                )
                % {"company": self.company_id.display_name}
            )
        return {
            "name": _("Apollo People Enrichment"),
            "type": "ir.actions.act_window",
            "res_model": "apollo.people.enrichment",
            "view_mode": "form",
            "target": "new",
            "context": {"default_partner_id": self.id},
        }
