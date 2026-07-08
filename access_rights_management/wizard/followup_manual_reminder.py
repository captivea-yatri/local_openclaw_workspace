from odoo import models


class FollowupManualReminder(models.TransientModel):
    _inherit = 'account_followup.manual_reminder'

    def process_followup(self):
        if self.env.user.has_group('access_rights_management.role_sales_hot') or self.env.user.has_group(
                'access_rights_management.role_administrative') or self.env.user.has_group(
                'access_rights_management.role_administrative_responsible') or self.env.user.has_group(
                'access_rights_management.role_management_control'):
            return super(FollowupManualReminder, self.sudo()).process_followup()
        else:
            return super(FollowupManualReminder, self).process_followup()
