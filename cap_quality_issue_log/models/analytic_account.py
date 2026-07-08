# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

#    def write(self, values):
#        """
#        Restrict timesheet update of developer on customer task
#        """
#        if values.get('unit_amount', False) and not \
#                self.env.user.has_group('cap_quality_issue_log.group_emp_perf_quality_recognizer') and \
#                not self.task_id.x_studio_final_task and self.x_studio_is_developer_time and self.project_id.id != 539:
#            raise ValidationError("You can not update development time. Instead create new task")
#        return super(AccountAnalyticLine, self).write(values)

#    def unlink(self):
#        """
#        Restrict timesheet deletion of developer on customer task
#        """
#        for rec in self:
#            if not self.env.user.has_group('cap_quality_issue_log.group_emp_perf_quality_recognizer') and not \
#                    rec.task_id.x_studio_final_task and rec.x_studio_is_developer_time and rec.project_id.id != 539:
#                raise ValidationError("You can not delete development timesheet.")
#        super(AccountAnalyticLine, self).unlink()
