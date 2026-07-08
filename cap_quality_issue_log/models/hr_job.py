# -*- coding: utf-8 -*-

from odoo import fields, api, models
from odoo.exceptions import ValidationError


class HrJob(models.Model):
    _inherit = "hr.job"

    onboard_prorata_ids = fields.One2many('on.boarding.prorata', 'job_id', string='On Boarding Pro-rata',
                                          groups='cap_quality_issue_log.group_emp_perf_quality_recognizer')


class OnBoardingProrata(models.Model):
    _name = "on.boarding.prorata"
    _description = "On Boarding Pro rata"

    # month_number = fields.Integer('Month')
    target_percentage = fields.Float('Target Percentage')
    job_id = fields.Many2one('hr.job', 'Job')

    @api.constrains('target_percentage')
    def onchange_planned_hours(self):
        for rec in self:
            if rec.target_percentage <= 0:
                raise ValidationError('Percentage must be greater than 0.')
