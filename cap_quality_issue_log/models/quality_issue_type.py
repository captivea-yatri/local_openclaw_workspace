# -*- coding: utf-8 -*-

from odoo import api, fields, models
from datetime import date


class QualityIssueType(models.Model):
    _name = "quality.issue.type"
    _description = "Quality Issue Type"

    name = fields.Char('Name')
    quality_category = fields.Many2one(comodel_name="quality.category")
    score_impact = fields.Float('Score Impact')
    action_performer = fields.Selection([('create_automated_action', 'Create Automated Action'),
                                         ('create_schedule_action', 'Create Schedule Action')])
    ir_cron_id = fields.Many2one('ir.cron', 'Schedule Action')
    base_automation_id = fields.Many2one('base.automation', 'Automated Action')
    ir_model_id = fields.Many2one('ir.model', 'Associated Object')
    state = fields.Selection([('draft', 'Draft'), ('in_progress', 'In Progress')], default='draft')

    def validate_issue_type(self):
        for rec in self.filtered(lambda rec: rec.state == 'draft'):
            if rec.action_performer == 'create_automated_action':
                automated_action_id = rec.env['base.automation'].create({'name': rec.name,
                                                                         'model_id': rec.ir_model_id.id,
                                                                         'state': 'code',
                                                                         'usage': 'base_automation',
                                                                         'trigger': 'on_create_or_write'})
                rec.write({'base_automation_id': automated_action_id.id, 'state': 'in_progress'})
            elif rec.action_performer == 'create_schedule_action':
                ir_cron_id = rec.env['ir.cron'].create({'name': rec.name,
                                                        'model_id': rec.ir_model_id.id,
                                                        'state': 'code',
                                                        'usage': 'ir_cron',
                                                        'user_id': rec.env.user and self.env.user.id or 2})
                rec.write({'ir_cron_id': ir_cron_id.id, 'state': 'in_progress'})

    def find_employee_based_on_company(self, user_id):
        return self.env['hr.employee'].search(
            [('user_id', '=', user_id.id), ('company_id', '=', user_id.company_id.id)])

    def check_planning_role(self, project_id, role_id, domain, msg, type, is_from_auto=False, project_feedback_id=False):
        if role_id.is_project_manager:
            if project_id.user_id:
                employee_id = self.find_employee_based_on_company(project_id.user_id)
                self.search_and_create_issue_log(domain, employee_id, role_id, msg, project_id, type, is_from_auto, project_feedback_id)
        elif role_id.is_business_analyst:
            for business_analyst in project_id.business_analyst_ids:
                employee_id = self.find_employee_based_on_company(business_analyst)
                self.search_and_create_issue_log(domain, employee_id, role_id, msg, project_id, type, is_from_auto, project_feedback_id)
        elif role_id.is_configurator:
            for configurator in project_id.configurators_ids:
                employee_id = self.find_employee_based_on_company(configurator)
                self.search_and_create_issue_log(domain, employee_id, role_id, msg, project_id, type, is_from_auto, project_feedback_id)
        elif role_id.is_developer:
            for developer in project_id.developers_ids:
                employee_id = self.find_employee_based_on_company(developer)
                self.search_and_create_issue_log(domain, employee_id, role_id, msg, project_id, type, is_from_auto, project_feedback_id)
        elif role_id.is_architect:
            for architect in project_id.architect_ids:
                employee_id = self.find_employee_based_on_company(architect)
                self.search_and_create_issue_log(domain, employee_id, role_id, msg, project_id, type, is_from_auto, project_feedback_id)

    def search_and_create_issue_log(self, domain, employee_id, role_id, msg, project_id, type,
                                    is_from_auto=False, feedback_id=False):
        today = date.today()
        issue_log_domain = [('employee_id', '=', employee_id.id),
                            ('quality_issue_type', '=', self.id), ('log_type', '=', type)]
        if role_id:
            issue_log_domain += [('role_id', '=', role_id.id)]
        if employee_id:
            issue_log_ids = self.env['quality.issue.log'].search(domain + issue_log_domain)
            if not issue_log_ids or is_from_auto == True:
                vals = {'logged_date': today,
                        'employee_id': employee_id.id,
                        'description': msg,
                        'quality_issue_type': self.id,
                        'project_id': project_id.id,
                        'role_id': role_id.id,
                        }
                if feedback_id:
                    vals.update({'feedback_id': feedback_id.id})
                if type == 'warning':
                    vals.update({'log_type': 'warning', 'score_impact': 0.00, 'state': 'warning'})
                else:
                    vals.update({'log_type': 'penalty', 'score_impact': self.score_impact,})
                self.env['quality.issue.log'].create(vals)

    def get_employee(self, project_id, role_ids):
        employee_id = self.env['hr.employee'].sudo()
        for role_id in role_ids:
            if role_id.is_project_manager and project_id.user_id:
                employee_id = self.find_employee_based_on_company(project_id.user_id)
            elif role_id.is_business_analyst:
                for business_analyst in project_id.business_analyst_ids:
                    employee_id = self.find_employee_based_on_company(business_analyst)
            elif role_id.is_configurator:
                for configurator in project_id.configurators_ids:
                    employee_id = self.find_employee_based_on_company(configurator)
            elif role_id.is_developer:
                for developer in project_id.developers_ids:
                    employee_id = self.find_employee_based_on_company(developer)
            elif role_id.is_architect:
                for architect in project_id.architect_ids:
                    employee_id = self.find_employee_based_on_company(architect)
            return employee_id
