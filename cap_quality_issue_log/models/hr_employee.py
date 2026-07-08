# -*- coding: utf-8 -*-

from odoo import fields, api, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    global_quality_score = fields.Float('Global Quality Score', groups="hr.group_hr_user")
    quality_score_message = fields.Html('Quality Score Info', groups="hr.group_hr_user")
    exclude_from_timesheet_quality_control = fields.Boolean('Exclude From Timesheet Quality Control', groups="hr.group_hr_user")
