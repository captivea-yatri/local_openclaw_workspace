from odoo import models, fields


class AccountOnlineLink(models.Model):
    _inherit = 'account.online.link'

    access_token = fields.Char(help="Token used to access API.", readonly=True,
                               groups="account.group_account_user,access_rights_management.role_management_control,access_rights_management.role_ceo,access_rights_management.role_administrative_responsible,access_rights_management.role_administrative")
