from odoo import api, fields, models, _


class Opportunity2Quotation(models.TransientModel):
    _inherit = 'crm.quotation.partner'

    def action_apply(self):
        if self.action == 'create' and self.env.user.has_group('access_rights_management.role_sales_hot'):
            self.lead_id.sudo()._handle_partner_assignment(create_missing=True)
        return super(Opportunity2Quotation, self).action_apply()
