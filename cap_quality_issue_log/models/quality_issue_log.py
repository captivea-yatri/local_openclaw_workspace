# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class QualityIssueLog(models.Model):
    _name = "quality.issue.log"
    _description = "Quality Issue Log"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'display_name'

    logged_date = fields.Date(string='Log Date', tracking=True)
    employee_id = fields.Many2one(comodel_name="hr.employee")
    project_id = fields.Many2one(comodel_name="project.project")
    description = fields.Text('Description')
    score_impact = fields.Float('Score Impact')
    quality_issue_type = fields.Many2one(comodel_name="quality.issue.type")
    state = fields.Selection([('warning', 'Warning'), ('enabled', 'Enabled'), ('disabled', 'Disabled'), ('reviewing', 'Reviewing')], 'Status',
                             default="enabled", tracking=True)
    company_id = fields.Many2one('res.company', compute='compute_company', store=True)
    is_valid_user = fields.Boolean(string='Is Access', compute='_compute_check_valid_user')
    role_id = fields.Many2one(comodel_name='planning.role', string='Role')
    timesheet_id = fields.Many2one(comodel_name='account.analytic.line', string='Timesheet')
    display_name = fields.Char(string='Display Name', compute='compute_display_name')
    log_type = fields.Selection([('warning', 'Warning'), ('penalty', 'Penalty')], string='Type')

    @api.depends('employee_id', 'quality_issue_type')
    def compute_display_name(self):
        for record in self:
            record.display_name = f"{record.employee_id.name} - {record.quality_issue_type.name}"


    def _compute_check_valid_user(self):
        for rec in self:
            if self.env.uid == rec.employee_id.parent_id.user_id.id or self.env.user.has_group(
                    'cap_quality_issue_log.group_emp_perf_quality_recognizer'):
                rec.is_valid_user = True
            else:
                rec.is_valid_user = False

    @api.depends('project_id', 'employee_id')
    def compute_company(self):
        for rec in self:
            if rec.project_id and rec.project_id.company_id:
                rec.company_id = rec.project_id.company_id.id
            elif rec.employee_id and rec.employee_id.company_id:
                rec.company_id = rec.employee_id.company_id.id
            else:
                rec.company_id = False

    def ask_for_review(self):
        for rec in self:
            activty_type = self.env['mail.activity.type'].search([('name', 'in', ['Todo', 'To Do', 'To-Do'])], limit=1)
            if activty_type and rec.employee_id.parent_id and rec.employee_id.parent_id.user_id:
                activity_id = self.env['mail.activity'].create({
                    'summary': 'Review Quality Issue',
                    'activity_type_id': activty_type.id,
                    'res_model_id': self.env['ir.model'].sudo().search([('model', '=', 'quality.issue.log')], limit=1).id,
                    'res_id': rec.id,
                    'user_id': rec.employee_id.parent_id.user_id.id
                })
                activity_id.action_close_dialog()
            rec.write({'state': 'reviewing'})

    def refuse_review(self):
        for rec in self:
            if rec.employee_id.parent_id.user_id.id == self.env.user.id or \
                    self.env.user.has_group('cap_quality_issue_log.group_emp_perf_quality_recognizer'):
                rec.write({'state': 'enabled'})
            else:
                raise ValidationError("Only employee manager or quality recognizer can review the score!")

    def accept_review(self):
        for rec in self:
            if rec.employee_id.parent_id.user_id.id == self.env.user.id or \
                    self.env.user.has_group('cap_quality_issue_log.group_emp_perf_quality_recognizer'):
                rec.write({'state': 'disabled'})
            else:
                raise ValidationError("Only employee manager or quality recognizer can review the score!")

    def action_open_approval_req(self):
        self.ensure_one()
        approval = self.env['approval.request'].search([
            ('x_studio_quality_issue_log', '=', self.id)
        ], limit=1)

        return {
            'name': 'Quality Issue Log Approval Request',
            'view_mode': 'list,form',
            'res_model': 'approval.request',
            'type': 'ir.actions.act_window',
            'res_id': approval.id,
            'target': 'current',
            'domain': [('x_studio_quality_issue_log', '=', self.id)],
        }
