# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import AccessError


class Survey(models.Model):
    _inherit = 'survey.survey'

    user_input_ids = fields.One2many('survey.user_input', 'survey_id', string='User responses', readonly=True,
                                     groups='survey.group_survey_user,access_rights_management.role_customer_referencer')

    def action_start_session(self):
        """ Sets the necessary fields for the session to take place and starts it.
        The write is sudo'ed because a survey user can start a session even if it's
        not their own survey. """

        if not self.env.user.has_group('survey.group_survey_user') and not self.env.user.has_group(
                'access_rights_management.role_customer_referencer'):
            raise AccessError(_('Only survey users can manage sessions.'))

        self.ensure_one()
        self.sudo().write({
            'questions_layout': 'page_per_question',
            'session_start_time': fields.Datetime.now(),
            'session_question_id': None,
            'session_state': 'ready'
        })
        return self.action_open_session_manager()


    def action_end_session(self):
        """ The write is sudo'ed because a survey user can end a session even if it's
        not their own survey. """

        if not self.env.user.has_group('survey.group_survey_user') and not self.env.user.has_group(
                'access_rights_management.role_customer_referencer'):
            raise AccessError(_('Only survey users can manage sessions.'))

        self.sudo().write({'session_state': False})
        self.user_input_ids.sudo().write({'state': 'done'})
        self.env['bus.bus']._sendone(self.access_token, 'end_session', {})
