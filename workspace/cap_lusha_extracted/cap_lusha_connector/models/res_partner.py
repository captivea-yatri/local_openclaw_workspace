# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    lusha_contact_id = fields.Char(
        string="Lusha Contact ID",
        copy=False,
        help="Lusha contact identifier from the last enrichment.",
    )
    lusha_company_id = fields.Char(
        string="Lusha Company ID",
        copy=False,
        help="Lusha company identifier from the last enrichment.",
    )

    def action_lusha_enrich_person(self):
        self.ensure_one()
        if not self.env["lusha.instance"].get_company_instance(self.company_id):
            raise UserError(
                _(
                    "No active Lusha instance is configured for company %(company)s."
                )
                % {"company": self.company_id.display_name}
            )
        return {
            "name": _("Lusha Contact Enrichment"),
            "type": "ir.actions.act_window",
            "res_model": "lusha.people.enrichment",
            "view_mode": "form",
            "target": "new",
            "context": {"default_partner_id": self.id},
        }
