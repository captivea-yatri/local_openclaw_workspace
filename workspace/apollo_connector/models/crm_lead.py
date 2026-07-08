# -*- coding: utf-8 -*-
"""Extend crm.lead with Apollo integration fields"""

from odoo import fields, models

class CrmLead(models.Model):
    """Add a hidden field to store the Apollo contact ID.
    This allows idempotent upserts during sync.
    """
    _inherit = "crm.lead"

    x_apollo_id = fields.Char(
        string="Apollo Contact ID",
        readonly=True,
        copy=False,
        index=True,
        help="Internal reference to the Apollo contact that created/updated this lead.",
    )
