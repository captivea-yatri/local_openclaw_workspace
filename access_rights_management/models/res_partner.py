from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.osv import expression


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_partner = fields.Boolean('Is Partner')
    is_applicant = fields.Boolean()
    followup_status = fields.Selection(
        [('in_need_of_action', 'In need of action'), ('with_overdue_invoices', 'With overdue invoices'),
         ('no_action_needed', 'No action needed')],
        compute='_compute_followup_status',
        string='Follow-up Status',
        search='_search_status',
        groups='account.group_account_readonly,account.group_account_invoice,access_rights_management.role_sales_hot,access_rights_management.role_vp_of_sales,access_rights_management.role_vps,access_rights_management.role_ceo,access_rights_management.role_management_control,access_rights_management.role_administrative_responsible,access_rights_management.role_administrative',
    )
    followup_line_id = fields.Many2one(
        comodel_name='account_followup.followup.line',
        string="Follow-up Level",
        compute='_compute_followup_status',
        inverse='_set_followup_line_on_unreconciled_amls',
        search='_search_followup_line',
        groups='account.group_account_readonly,account.group_account_invoice,access_rights_management.role_sales_hot,access_rights_management.role_ceo',
    )
    total_invoiced = fields.Monetary(compute='_invoice_total', string="Total Invoiced",
                                     groups='account.group_account_invoice,account.group_account_readonly,access_rights_management.role_management_control,access_rights_management.role_administrative_responsible,access_rights_management.role_administrative,access_rights_management.role_sales_hot,access_rights_management.role_vps,access_rights_management.role_vp_of_sales,access_rights_management.role_ceo')
    opportunity_count = fields.Integer("Opportunity", compute='_compute_opportunity_count', compute_sudo=True ,groups='base.group_user')
    total_due = fields.Monetary(
        compute='_compute_total_due',
        groups='account.group_account_readonly,account.group_account_invoice,access_rights_management.role_sales_hot,access_rights_management.role_management_control,access_rights_management.role_administrative_responsible,access_rights_management.role_administrative,access_rights_management.role_vps,access_rights_management.role_vp_of_sales,access_rights_management.role_ceo')
    total_overdue = fields.Monetary(
        compute='_compute_total_due',
        groups='account.group_account_readonly,account.group_account_invoice,access_rights_management.role_sales_hot,access_rights_management.role_management_control,access_rights_management.role_administrative_responsible,access_rights_management.role_administrative,access_rights_management.role_vps,access_rights_management.role_vp_of_sales,access_rights_management.role_ceo')
    accounting_information = fields.Boolean("Accounting Information", default=True)
    project_information = fields.Boolean("Project Information", default=True)
    user_allowed_company_ids = fields.Many2many('res.company', string="Companies",
                                                relation='res_company_res_partner_rel')
    is_portal_user = fields.Boolean(string="Is Portal User", compute='_compute_is_portal_user', store=True,
                                    compute_sudo=True, default=False)
    sale_order_count = fields.Integer(
        string="Sale Order Count",
        groups='sales_team.group_sale_salesman,access_rights_management.role_cfo,access_rights_management.role_team_director,access_rights_management.role_team_manager,access_rights_management.role_operation,access_rights_management.role_operation_on_boarder,access_rights_management.role_administrative,access_rights_management.role_administrative_responsible,access_rights_management.role_management_control,access_rights_management.role_sales_hot',
        compute='_compute_sale_order_count',
    )
    credit_limit = fields.Float(
        string='Credit Limit', help='Credit limit specific to this partner.',
        groups='account.group_account_invoice,account.group_account_readonly,access_rights_management.role_vp_of_marketing,access_rights_management.role_it_person,access_rights_management.role_ceo',
        company_dependent=True, copy=False, readonly=False)
    show_credit_limit = fields.Boolean(
        default=lambda self: self.env.company.account_use_credit_limit,
        compute='_compute_show_credit_limit', groups='account.group_account_invoice,account.group_account_readonly,access_rights_management.role_ceo')
    use_partner_credit_limit = fields.Boolean(
        string='Partner Limit', groups='account.group_account_invoice,account.group_account_readonly,access_rights_management.role_ceo',
        compute='_compute_use_partner_credit_limit', inverse='_inverse_use_partner_credit_limit',
        help='Set a value greater than 0.0 to activate a credit limit check')
    followup_responsible_id = fields.Many2one(
        comodel_name='res.users',
        string='Responsible',
        help="The responsible assigned to manual followup activities, if defined in the level.",
        tracking=True,
        copy=False,
        company_dependent=True,
        groups='account.group_account_readonly,account.group_account_invoice,access_rights_management.role_ceo',
    )


    def _compute_sale_order_count(self):
        if self.env.user.has_group('access_rights_management.role_cfo') or self.env.user.has_group(
                'access_rights_management.role_team_director') or self.env.user.has_group(
            'access_rights_management.role_team_manager') or self.env.user.has_group(
            'access_rights_management.role_operation') or self.env.user.has_group(
            'access_rights_management.role_operation_on_boarder') or self.env.user.has_group(
            'access_rights_management.role_administrative') or self.env.user.has_group(
            'access_rights_management.role_administrative_responsible') or self.env.user.has_group(
            'access_rights_management.role_management_control'):

            self.sale_order_count = 0
            all_partners = self.with_context(active_test=False).search_fetch(
                [('id', 'child_of', self.ids)],
                ['parent_id'],
            )
            sale_order_groups = self.env['sale.order']._read_group(
                domain=expression.AND([self._get_sale_order_domain_count(), [('partner_id', 'in', all_partners.ids)]]),
                groupby=['partner_id'], aggregates=['__count']
            )
            self_ids = set(self._ids)

            for partner, count in sale_order_groups:
                while partner:
                    if partner.id in self_ids:
                        partner.sale_order_count += count
                    partner = partner.parent_id
        else:
            super(ResPartner, self)._compute_sale_order_count()

    @api.depends('user_ids', 'user_ids.share')
    def _compute_is_portal_user(self):
        for record in self:
            record.is_portal_user = record.user_ids.filtered(lambda u: u.share)

    def change_expected_date(self, options=False):
        if self.env.user.has_group('access_rights_management.role_management_control') or self.env.user.has_group(
                'access_rights_management.role_administrative_responsible') or self.env.user.has_group(
            'access_rights_management.role_administrative'):
            return super(ResPartner, self.sudo()).change_expected_date(options)
        else:
            return super(ResPartner, self).change_expected_date(options)

    @api.constrains('user_allowed_company_ids')
    def _check_user_allowed_company_ids(self):
        for record in self:
            if record.user_ids.filtered(lambda u: u.share) and not record.user_allowed_company_ids:
                raise ValidationError("You must add at least one company for Allowed Companies for user field.")

    def write(self, vals):
        if self.env.context.get('from_user_write', False):
            return super(ResPartner, self).write(vals)

        res = super(ResPartner, self).write(vals)
        for rec in self:
            if 'user_allowed_company_ids' in vals:
                for user in rec.user_ids.filtered(lambda u: u.share):
                    values = {
                        'company_ids': [(6, 0, rec.user_allowed_company_ids.ids)] if rec.user_allowed_company_ids else [
                            (6, 0, user.company_ids.ids)]}
                    if not user.company_id or (user.company_id not in rec.user_allowed_company_ids):
                        values.update({'company_id': rec.user_allowed_company_ids.sorted('sequence')[
                            0].id if rec.user_allowed_company_ids else user.company_id.id})
                    user.with_context(from_partner_write=True).sudo().write(values)
        return res
