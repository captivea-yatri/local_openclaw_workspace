from odoo import fields, models, api, Command
from datetime import date
import dateutil


class Project(models.Model):
    _inherit = 'project.project'

    def go_live_date_passed(self):
        cron_id = self.env.ref('cap_quality_issue_log.ir_cron_go_live_date_passed')
        issue_type = self.env['quality.issue.type'].search([('ir_cron_id', '=', cron_id.id)])
        today = fields.Date.today()
        first_day_of_the_month = today.replace(day=1)
        quality_category = issue_type.quality_category
        project_ids = self.search(['|', ('project_status_id', '=', False), ('project_status_id.code', 'not in',
                                    ['live', 'dead', 'duplicate', 'internal', 'internal_p2p3']),
                                   ('active', '=', True), ('partner_id', '!=', False), ('partner_id', '!=', 1),
                                   ('user_id', '!=', False), ('on_hold_reason', '=', False),
                                   ('exclude_for_go_live', '=', False)])
        date_last_week = today + dateutil.relativedelta.relativedelta(days=-7)
        for project_id in project_ids:
            if quality_category.warning_before_penalty:
                date_before_4_days = today + dateutil.relativedelta.relativedelta(days=-4)
                if not project_id.x_studio_go_live_date and project_id.create_date.date() < date_before_4_days:
                    domain = [('project_id', '=', project_id.id), ('logged_date', '>=', first_day_of_the_month)]
                    msg = "WARNING: \nThe Go Live date for the project : {} has not been set. If the Go Live date remains unset, a Penalty quality issue will be raised.".format(project_id.name)
                    type = 'warning'
                    if quality_category.role_ids:
                        for role_id in quality_category.role_ids:
                            issue_type.check_planning_role(project_id, role_id, domain, msg, type)
                    else:
                        employee_id = issue_type.find_employee_based_on_company(project_id.user_id)
                        role_id = self.env['planning.role'].search([('is_project_manager', '=', True)])
                        issue_type.search_and_create_issue_log(domain, employee_id, role_id, msg, project_id, type)
                if project_id.x_studio_go_live_date and project_id.x_studio_go_live_date < date_before_4_days:
                    domain = [('project_id', '=', project_id.id), ('logged_date', '>=', first_day_of_the_month)]
                    msg = "WARNING: \nGo live date for : {} is passed before 4 Days".format(project_id.name)
                    type = 'warning'
                    if quality_category.role_ids:
                        for role_id in quality_category.role_ids:
                            issue_type.check_planning_role(project_id, role_id, domain, msg, type)
                    else:
                        employee_id = issue_type.find_employee_based_on_company(project_id.user_id)
                        role_id = self.env['planning.role'].search([('is_project_manager', '=', True)])
                        issue_type.search_and_create_issue_log(domain, employee_id, role_id, msg, project_id, type)

            employee_id = issue_type.get_employee(project_id, quality_category.role_ids)
            last_warning_log = self.env['quality.issue.log'].search(
                [('project_id', '=', project_id.id), ('log_type', '=', 'warning'), ('employee_id', '=', employee_id.id),
                 ('quality_issue_type', '=', issue_type.id)], order='id desc', limit=1)
            if not quality_category.warning_before_penalty or (
                    last_warning_log and last_warning_log.logged_date + dateutil.relativedelta.relativedelta(
                    days=3) <= today):
                if not project_id.x_studio_go_live_date and project_id.create_date.date() < date_last_week:
                    domain = [('project_id', '=', project_id.id), ('logged_date', '>=', first_day_of_the_month)]
                    msg = "The Go Live date for the project : {} has not been set".format(project_id.name)
                    type = 'penalty'
                    if quality_category.role_ids:
                        for role_id in quality_category.role_ids:
                            issue_type.check_planning_role(project_id, role_id, domain, msg, type)
                    else:
                        employee_id = issue_type.find_employee_based_on_company(project_id.user_id)
                        role_id = self.env['planning.role'].search([('is_project_manager', '=', True)])
                        issue_type.search_and_create_issue_log(domain, employee_id, role_id, msg, project_id, type)
                if project_id.x_studio_go_live_date and project_id.x_studio_go_live_date < date_last_week:
                    first_day_of_the_month = today.replace(day=1)
                    domain = [('project_id', '=', project_id.id), ('logged_date', '>=', first_day_of_the_month)]
                    msg = 'Go live date for : {} is passed before 7 Days'.format(project_id.name)
                    type = 'penalty'
                    if quality_category.role_ids:
                        for role_id in quality_category.role_ids:
                            issue_type.check_planning_role(project_id, role_id, domain, msg, type)
                    else:
                        employee_id = issue_type.find_employee_based_on_company(project_id.user_id)
                        role_id = self.env['planning.role'].search([('is_project_manager', '=', True)])
                        issue_type.search_and_create_issue_log(domain, employee_id, role_id, msg, project_id, type)

    def check_project_status(self):
        cron_id = self.env.ref('cap_quality_issue_log.ir_cron_status_on_project')
        issue_type = self.env['quality.issue.type'].search([('ir_cron_id', '=', cron_id.id)])
        project_ids = self.search([('project_status_id', '=', False), ('on_hold_reason', '=', False)])
        quality_category = issue_type.quality_category
        today = fields.Date.today()
        first_day_of_the_month = today.replace(day=1)
        for project_id in project_ids:
            employee_id = issue_type.get_employee(project_id, quality_category.role_ids)
            if quality_category.warning_before_penalty:
                last_penalty_log = self.env['quality.issue.log'].search(
                    [('log_type', '=', 'penalty'), ('employee_id', '=', employee_id.id),
                     ('quality_issue_type', '=', issue_type.id)], order='id desc', limit=1)
                if not last_penalty_log or (last_penalty_log and last_penalty_log.logged_date + dateutil.relativedelta.relativedelta(days=4) <= today):
                    domain = [('project_id', '=', project_id.id), ('logged_date', '>=', first_day_of_the_month)]
                    msg = "WARNING: \nStatus of Project : {} is Empty, If the Status of Project remains Empty, a Penalty quality issue will be raised.".format(project_id.name)
                    type = 'warning'
                    if quality_category.role_ids:
                        for role_id in quality_category.role_ids:
                            issue_type.check_planning_role(project_id, role_id, domain, msg, type)
                    else:
                        employee_id = issue_type.find_employee_based_on_company(project_id.user_id)
                        role_id = self.env['planning.role'].search([('is_project_manager', '=', True)])
                        issue_type.search_and_create_issue_log(domain, employee_id, role_id, msg, project_id, type)

            last_warning_log = self.env['quality.issue.log'].search(
                [('project_id', '=', project_id.id), ('log_type', '=', 'warning'), ('employee_id', '=', employee_id.id),
                 ('quality_issue_type', '=', issue_type.id)], order='id desc', limit=1)
            if not quality_category.warning_before_penalty or (
                    last_warning_log and last_warning_log.logged_date + dateutil.relativedelta.relativedelta(
                    days=3) <= today):
                domain = [('project_id', '=', project_id.id), ('logged_date', '>=', first_day_of_the_month)]
                msg = "Status of Project : {} is Empty".format(project_id.name)
                type = 'penalty'
                if quality_category.role_ids:
                    for role_id in quality_category.role_ids:
                        issue_type.check_planning_role(project_id, role_id, domain, msg, type)
                else:
                    employee_id = issue_type.find_employee_based_on_company(project_id.user_id)
                    role_id = self.env['planning.role'].search([('is_project_manager', '=', True)])
                    issue_type.search_and_create_issue_log(domain, employee_id, role_id, msg, project_id, type)
