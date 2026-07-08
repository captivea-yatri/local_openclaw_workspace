from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = "account.move"

    invoice_outstanding_credits_debits_widget = fields.Binary(
        groups="account.group_account_invoice,account.group_account_readonly,access_rights_management.role_management_control,access_rights_management.role_administrative_responsible,access_rights_management.role_administrative,access_rights_management.role_vps,access_rights_management.role_vp_of_sales,access_rights_management.role_ceo",
        compute='_compute_payments_widget_to_reconcile_info',
        exportable=False,
    )
    invoice_payments_widget = fields.Binary(
        groups="account.group_account_invoice,account.group_account_readonly,access_rights_management.role_management_control,access_rights_management.role_administrative_responsible,access_rights_management.role_administrative,access_rights_management.role_vps,access_rights_management.role_vp_of_sales,access_rights_management.role_ceo",
        compute='_compute_payments_widget_reconciled_info',
        exportable=False,
    )
    # TODO : need to check in database related to this field and button register payment
    invoice_has_outstanding = fields.Boolean(
        groups="account.group_account_invoice,account.group_account_readonly,access_rights_management.role_management_control,access_rights_management.role_administrative_responsible,access_rights_management.role_administrative,access_rights_management.role_vps,access_rights_management.role_vp_of_sales,access_rights_management.role_ceo",
        compute='_compute_payments_widget_to_reconcile_info',
    )

    def action_post(self):
        for record in self:
            if record.state == 'draft' and record.move_type == 'out_invoice':
                variable_cost_products = list({
                    line.product_id.display_name
                    for line in record.invoice_line_ids
                    if line.product_id.product_variable_cost
                })
                if variable_cost_products:
                    if not record.company_id.administrative_responsible:
                        raise UserError(
                            _("Please set a Administrative Responsible in the company settings as this invoice contains products with variable costs."))

                    product_list = "\n".join(
                        [f"{i + 1}). {name}" for i, name in enumerate(variable_cost_products)]
                    )
                    note = f"Products with variable cost:\n{product_list}"

                    self.env['mail.activity'].create({
                        'activity_type_id': record.env.ref('mail.mail_activity_data_todo').id,
                        'res_model_id': record.env['ir.model'].sudo().search([('model', '=', 'account.move')],
                                                                             limit=1).id,
                        'res_id': record.id,
                        'user_id': record.company_id.administrative_responsible.id,
                        'summary': 'Confirm Variable Cost Product',
                        'note': note,
                    })

        if self.env.user.has_group('access_rights_management.role_sales_hot') or self.env.user.has_group(
                'access_rights_management.role_administrative_responsible') or self.env.user.has_group(
            'access_rights_management.role_administrative') or self.env.user.has_group(
            'access_rights_management.role_management_control') or self.env.user.has_group(
            'access_rights_management.role_ceo') or self.env.user.has_group(
            'access_rights_management.role_vp_of_marketing') or self.env.user.has_group(
            'access_rights_management.role_vp_of_sales'):
            return super(AccountMove, self.sudo()).action_post()
        else:
            return super(AccountMove, self).action_post()

    def _post(self, soft=True):
        if self.env.user.has_group('access_rights_management.role_sales_hot') or self.env.user.has_group(
                'access_rights_management.role_administrative_responsible') or self.env.user.has_group(
            'access_rights_management.role_administrative') or self.env.user.has_group(
            'access_rights_management.role_management_control') or self.env.user.has_group(
            'access_rights_management.role_ceo') or self.env.user.has_group(
            'access_rights_management.role_vp_of_marketing'):
            return super(AccountMove, self.sudo())._post(soft)
        else:
            return super(AccountMove, self)._post(soft)


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _inverse_analytic_distribution(self):
        if self.env.user.has_group(
                'access_rights_management.role_administrative_responsible') or self.env.user.has_group(
            'access_rights_management.role_administrative') or self.env.user.has_group(
                'access_rights_management.role_management_control') or self.env.user.has_group(
                'access_rights_management.role_ceo'):
            return super(AccountMoveLine, self.sudo())._inverse_analytic_distribution()
        else:
            return super(AccountMoveLine, self)._inverse_analytic_distribution()
