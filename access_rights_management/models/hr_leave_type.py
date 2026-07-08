from odoo import models, fields, api

class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'

    no_adjustment_on_target = fields.Boolean('No Adjustment on Target')