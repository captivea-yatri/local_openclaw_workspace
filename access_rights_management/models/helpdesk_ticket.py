from odoo import models, fields, api, Command


class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.ticket'

    @api.model_create_multi
    def create(self, vals_list):
        res = super(HelpdeskTicket, self).create(vals_list)
        for record in res:
            if record.team_id and record.team_id.create_activity and record.user_id:
                self.env['mail.activity'].create({
                    'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                    'res_model_id': self.env['ir.model'].sudo().search([('model', '=', 'helpdesk.ticket')],
                                                                    limit=1).id,
                    'res_id': record.id,
                    'user_id': record.user_id.id,
                    'summary': 'Support Request',
                })
        return res

    @api.depends('team_id')
    def _compute_domain_user_ids(self):
        user_ids = self.env['res.users'].search(
            ['|', '|', '|', '|', '|', '|', '|', ('id', 'in', self.env.ref('helpdesk.group_helpdesk_user').users.ids),
             ('id', 'in', self.env.ref('access_rights_management.show_helpdesk').users.ids),
             ('id', 'in', self.env.ref('access_rights_management.role_ceo').users.ids),
             ('id', 'in', self.env.ref('access_rights_management.role_vp_of_sales').users.ids),
             ('id', 'in', self.env.ref('access_rights_management.role_vps').users.ids),
             ('id', 'in', self.env.ref('access_rights_management.role_sales_cold').users.ids),
             ('id', 'in', self.env.ref('access_rights_management.role_sales_cold_team_manager').users.ids),
             ('id', 'in', self.env.ref('access_rights_management.role_sales_cold_team_director').users.ids)]).ids
        for ticket in self:
            ticket_user_ids = []
            ticket_sudo = ticket.sudo()
            if ticket_sudo.team_id and ticket_sudo.team_id.privacy_visibility == 'invited_internal':
                ticket_user_ids = ticket_sudo.team_id.message_partner_ids.user_ids.ids
            ticket.domain_user_ids = [Command.set(user_ids + ticket_user_ids)]
