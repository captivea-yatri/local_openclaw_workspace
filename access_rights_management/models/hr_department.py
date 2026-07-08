from odoo import models, fields, api


class HrDepartment(models.Model):
    _inherit = "hr.department"

    analytic_account_id = fields.Many2one('account.analytic.account',domain="[('plan_id.id','=','14')]",string='Analytic Account',tracking=True)