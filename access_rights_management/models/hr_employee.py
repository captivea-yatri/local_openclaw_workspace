from odoo import models, _, fields
from odoo.exceptions import UserError


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    has_timesheet = fields.Boolean(compute='_compute_has_timesheet', groups="hr.group_hr_user,base.group_system,hr_timesheet.group_hr_timesheet_user",
                                   export_string_translation=False)
    departure_description = fields.Html(string="Additional Information", groups="hr.group_hr_user,access_rights_management.role_webmaster", copy=False)
    quality_score_message = fields.Html('Quality Score Info', groups="hr.group_hr_user,access_rights_management.role_webmaster")

    def get_last_validated_timesheet_date(self):
        """
        need to override this method for the roles who don't have group for timesheet but want to see timesheet.
        """
        if self.env.user.has_group('hr_timesheet.group_timesheet_manager'):
            return {}
        if not (self.env.user.has_group('access_rights_management.role_cashflow_manager') or
                self.env.user.has_group('access_rights_management.role_budget_manager') or
                self.env.user.has_group('access_rights_management.role_legal')):
            if not self.env.user.has_group('hr_timesheet.group_hr_timesheet_user'):
                raise UserError(_('You are not allowed to see timesheets.'))

        return {
            employee.id: employee.last_validated_timesheet_date
            for employee in self.sudo()
        }

    def write(self, vals):
        if 'last_validated_timesheet_date' in vals:
            vals['last_validated_timesheet_date'] = False
        return super(HrEmployee, self).write(vals)

class HrEmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    def open_internal_project_quotas(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("access_rights_management.action_view_internal_project_quota_from_public_employee")
        action['domain'] = [('employee_id', '=', self.employee_id.id)]
        action['context'] = {'default_employee_id': self.employee_id.id}
        return action