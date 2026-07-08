from odoo import fields, models

class ResCompany(models.Model):
    _inherit = 'res.company'

    administrative_responsible = fields.Many2one('res.users', 'Administrative Responsible')
