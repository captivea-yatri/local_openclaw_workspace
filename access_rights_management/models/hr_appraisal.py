# -*- coding: utf-8 -*-

from odoo import fields, models, api


class HrAppraisal(models.Model):
    _inherit = "hr.appraisal"

    employee_feedback = fields.Html(compute='_compute_employee_feedback', store=True, readonly=False,
                                    groups="hr_appraisal.group_hr_appraisal_user,access_rights_management.role_webmaster")
    manager_feedback = fields.Html(compute='_compute_manager_feedback', store=True, readonly=False,
                                   groups="hr_appraisal.group_hr_appraisal_user,access_rights_management.role_webmaster")
