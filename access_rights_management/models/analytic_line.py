from odoo import models, fields, api, _
from odoo.exceptions import AccessError, UserError


class AnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    allow_billable = fields.Boolean(related='project_id.allow_billable')

    def unlink(self):
        """
        Here, We Checked three conditions on which he can delete the timesheets:
        1.If Current User is a PM of that particular project.
        2.He will be able to delete the timesheets of his child employees.
        3.He will be able to delete his own timesheets.
        """
        if self.env.user.has_group('access_rights_management.role_hr') or self.env.user.has_group(
                'access_rights_management.role_hr_responsible'):
            for analytic_line in self:
                timeoff_type_ids = self.env['hr.leave.type'].sudo().search(
                    [('company_id', '=', analytic_line.company_id.id),
                     ('timesheet_project_id', '=', analytic_line.project_id.id),
                     ('timesheet_task_id', '=', analytic_line.task_id.id)])
                if timeoff_type_ids:
                    return super(AnalyticLine, self).unlink()
                else:
                    raise AccessError(_("You cannot delete timesheet that are not yours!!!"))
        elif (not self.env.user.has_group('access_rights_management.role_president') and not self.env.user.has_group(
                'access_rights_management.role_cfo') and not self.env.user.has_group(
            'access_rights_management.role_vp_of_quality_and_knowledge') and not self.env.user.has_group(
            'access_rights_management.role_ceo') and not self.env.user.has_group(
            'access_rights_management.role_administrative') and not self.env.user.has_group(
            'access_rights_management.role_administrative_responsible') and not self.env.user.has_group(
            'access_rights_management.role_management_control') and not self.env.user.has_group(
            'access_rights_management.role_it_person') and not self.env.user.has_group('access_rights_management.role_drh')) and any(
            self.env.user.id != analytic_line.project_id.user_id.id and self.env.user.id != analytic_line.employee_id.parent_id.user_id.id and self.env.user.id != analytic_line.employee_id.user_id.id and analytic_line.project_id and analytic_line.task_id and analytic_line.employee_id
            for analytic_line in self):
            raise AccessError(_("You cannot delete timesheet that are not yours!!!"))
        else:
            return super(AnalyticLine, self).unlink()

    def _is_not_billed(self):
        if self.env.user.has_group('access_rights_management.role_team_manager') or self.env.user.has_group(
                'access_rights_management.role_team_director') or self.env.user.has_group(
            'access_rights_management.role_operation') or self.env.user.has_group(
            'access_rights_management.role_operation_on_boarder') or self.env.user.has_group(
            'access_rights_management.role_hr') or self.env.user.has_group(
            'access_rights_management.role_hr_responsible'):
            return super(AnalyticLine, self.sudo())._is_not_billed()
        else:
            return super(AnalyticLine, self)._is_not_billed()

    @api.ondelete(at_uninstall=False)
    def _unlink_except_linked_leave(self):
        if self.env.user.has_group('access_rights_management.role_administrative') or self.env.user.has_group(
                'access_rights_management.role_hr') or self.env.user.has_group(
            'access_rights_management.role_hr_responsible') or self.env.user.has_group(
            'access_rights_management.role_drh'):
            pass
        else:
            if any(line.holiday_id for line in self):
                raise UserError(
                    _('You cannot delete timesheets that are linked to time off requests. Please cancel your time off request from the Time Off application instead.'))

    @api.ondelete(at_uninstall=False)
    def _unlink_if_manager(self):
        if self.env.user.has_group('access_rights_management.role_drh') or self.env.user.has_group(
                'access_rights_management.role_administrative') or self.env.user.has_group(
            'access_rights_management.role_administrative_responsible') or self.env.user.has_group(
            'access_rights_management.role_hr') or self.env.user.has_group(
            'access_rights_management.role_hr_responsible'):
            self.check_if_allowed(delete=True)
        elif not self.env.user.has_group('hr_timesheet.group_hr_timesheet_approver') and self.filtered(
                lambda r: r.is_timesheet and r.validated):
            raise AccessError(
                _('You cannot delete a validated entry. Please, contact your manager or your timesheet approver.'))

        self.check_if_allowed(delete=True)

    def _timesheet_get_portal_domain(self):
        """
        For the portal user: manage multi company record rule.
        """
        if self.env.user.has_group('base.group_portal'):
            return [ '&', ('company_id', 'in', self.env.user.company_ids.ids),
                '|',
                    '&',
                        '|',
                            ('task_id.project_id.message_partner_ids', 'child_of', [self.env.user.partner_id.commercial_partner_id.id]),
                            ('task_id.message_partner_ids', 'child_of', [self.env.user.partner_id.commercial_partner_id.id]),
                        ('task_id.project_id.privacy_visibility', '=', 'portal'),
                    '&',
                        ('task_id', '=', False),
                        '&',
                            ('project_id.message_partner_ids', 'child_of', [self.env.user.partner_id.commercial_partner_id.id]),
                            ('project_id.privacy_visibility', '=', 'portal'),
            ]
        else:
            return super(AnalyticLine, self)._timesheet_get_portal_domain()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            holiday_id = vals.get('holiday_id')
            if holiday_id:
                holiday = self.env['hr.leave'].browse(holiday_id)
                if holiday.holiday_status_id.no_adjustment_on_target:
                    if holiday.request_unit_half:
                        time_off_amount = holiday.employee_id.job_id.x_studio_ptoholidays_impact / 2
                    else:
                        time_off_amount = holiday.employee_id.job_id.x_studio_ptoholidays_impact
                    vals['unit_amount'] = time_off_amount

        res = super(AnalyticLine, self).create(vals_list)
        return res

