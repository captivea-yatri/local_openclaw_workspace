from odoo import models, fields, api, _


class Users(models.Model):
    _inherit = "res.users"

    def _is_system(self):
        res = super(Users, self)._is_system()
        if self.env.context.get('is_access') and (self.env.user.has_group(
                'access_rights_management.role_marketing_manager') or self.env.user.has_group(
            'access_rights_management.role_email_manager') or self.env.user.has_group(
            'access_rights_management.role_community_manager') or self.env.user.has_group(
            'access_rights_management.role_vp_of_sales') or self.env.user.has_group(
            'access_rights_management.role_ceo') or self.env.user.has_group(
            'access_rights_management.role_vp_of_marketing') or self.env.user.has_group(
            'access_rights_management.role_marketing_assistant')):
            return self.has_group('base.group_user')
        else:
            return res

    @api.model_create_multi
    def create(self, vals_list):
        res = super(Users, self).create(vals_list)
        for rec in res.filtered(lambda rec: rec.share):
            if rec.partner_id.user_allowed_company_ids:
                rec.company_ids = [(4, company_id.id) for company_id in rec.partner_id.user_allowed_company_ids]
                rec.company_id = rec.partner_id.user_allowed_company_ids.sorted('sequence')[0].id
            elif not rec.partner_id.user_allowed_company_ids:
                rec.partner_id.user_allowed_company_ids = [(6, 0, rec.company_ids.ids)]
            for company_id in rec.company_ids:
                if rec.partner_id.user_allowed_company_ids and company_id not in rec.partner_id.user_allowed_company_ids:
                    rec.company_ids = [(3, company_id.id)]
        return res

    def write(self, vals):
        if self.env.context.get('from_partner_write', False):
            return super(Users, self).write(vals)
        res = super(Users, self).write(vals)
        for user in self.filtered(lambda u: u.share):
            if 'company_ids' in vals or 'sel_groups_1_9_10' in vals:
                user.partner_id.with_context(from_user_write=True).write({
                    'user_allowed_company_ids': [(6, 0, user.company_ids.ids)]
                })
        return res
