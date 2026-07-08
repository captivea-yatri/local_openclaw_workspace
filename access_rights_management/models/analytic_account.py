from odoo import api, fields, models


class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    balance = fields.Monetary(
        compute='_compute_debit_credit_balance',
        string='Balance',
        groups='account.group_account_readonly,access_rights_management.role_management_control,access_rights_management.role_administrative_responsible,access_rights_management.role_administrative'
    )
