from odoo import api, fields, models, Command, SUPERUSER_ID
from datetime import date
import dateutil


class ProjectProgress(models.Model):
    _inherit = 'project.progress'

    def pm_report_not_done(self):
        cron_id = self.env.ref('cap_quality_issue_log.ir_cron_pm_report_not_done')
        issue_type = self.env['quality.issue.type'].search([('ir_cron_id', '=', cron_id.id)])
        quality_category = issue_type.quality_category
        today = date.today()
        seven_days_before = today + dateutil.relativedelta.relativedelta(days=-7)

        project_ids = self.env['project.project'].search(
            [('no_pm_report', '=', False), ('on_hold_reason', '=', False), '|', ('project_status_id', '=', False),
             ('project_status_id.code', 'not in', ['dead', 'duplicate', 'internal', 'internal_p2p3'])])
        for project_id in project_ids:
            employee_id = issue_type.get_employee(project_id, quality_category.role_ids)
            if quality_category.warning_before_penalty:
                first_day_of_the_month = today.replace(day=1)
                date_before = today + dateutil.relativedelta.relativedelta(days=-project_id.report_frequency_in_days)
                if project_id.create_date.date() <= date_before:
                    project_progress_ids = self.env['project.progress'].search(
                        [('project_id', '=', project_id.id), ('create_date', '>=', date_before),
                         ('status', 'in', ['sent', 'signed'])])
                    last_penalty_log = self.env['quality.issue.log'].search(
                        [('project_id', '=', project_id.id), ('quality_issue_type', '=', issue_type.id),
                         ('log_type', '=', 'penalty'), ('employee_id', '=', employee_id.id)],
                        order='id desc', limit=1)
                    if not last_penalty_log or (last_penalty_log and last_penalty_log.logged_date + dateutil.relativedelta.relativedelta(days=4) <= today):
                        if not project_progress_ids:
                            domain = [('project_id', '=', project_id.id), ('logged_date', '<=', today),
                                      ('logged_date', '>=', first_day_of_the_month)]
                            msg = "WARNING: \nPM report is not created, or status is not in Sent or Signed for project: {}, If PM report is still not created, or status is not in Sent or Signed, a Penalty quality issue will be raised.\n".format(project_id.name)
                            type = 'warning'
                            if quality_category.role_ids:
                                for role_id in quality_category.role_ids:
                                    issue_type.check_planning_role(project_id, role_id, domain, msg, type)
                            else:
                                employee_id = issue_type.find_employee_based_on_company(project_id.user_id)
                                role_id = self.env['planning.role'].search([('is_project_manager', '=', True)])
                                issue_type.search_and_create_issue_log(domain, employee_id, role_id, msg, project_id, type)

            last_warning_log = self.env['quality.issue.log'].search(
                [('employee_id', '=', employee_id.id), ('project_id', '=', project_id.id), ('log_type', '=', 'warning'),
                 ('quality_issue_type', '=', issue_type.id)],
                order='id desc', limit=1)
            if not quality_category.warning_before_penalty or (
                    last_warning_log and last_warning_log.logged_date + dateutil.relativedelta.relativedelta(
                    days=3) <= today):
                days_before = today + dateutil.relativedelta.relativedelta(days=-(3 + project_id.report_frequency_in_days))
                if project_id.create_date.date() <= days_before:
                    project_progress_ids = self.env['project.progress'].search(
                        [('project_id', '=', project_id.id), ('create_date', '>=', days_before),('status', 'in', ['sent','signed'])])
                    if not project_progress_ids:
                        domain = [('project_id', '=', project_id.id), ('logged_date', '>=', seven_days_before),
                                  ('logged_date', '<=', today)]
                        msg = 'Log is created due to PM report is not created, or status is not in Sent or Signed : {}'.format(project_id.name)
                        type = 'penalty'
                        if quality_category.role_ids:
                            for role_id in quality_category.role_ids:
                                issue_type.check_planning_role(project_id, role_id, domain, msg, type)
                        else:
                            employee_id = issue_type.find_employee_based_on_company(project_id.user_id)
                            role_id = self.env['planning.role'].search([('is_project_manager', '=', True)])
                            issue_type.search_and_create_issue_log(domain, employee_id, role_id, msg, project_id, type)
