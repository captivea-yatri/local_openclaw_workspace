# -*- coding: utf-8 -*-
from odoo import fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    lusha_contact_id = fields.Char(
        string="Lusha Contact ID",
        copy=False,
        index=True,
        help="Lusha contact identifier used to avoid duplicate lead imports.",
    )
