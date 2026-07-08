from odoo import models, api


class VoipPhonecall(models.Model):
    _inherit = "voip.phonecall"

    @api.model
    def get_recent_list(self, search_expr=None, offset=0, limit=None):
        """
        To avoid voip recent tab access error.
        """
        return super(VoipPhonecall, self.sudo()).get_recent_list(search_expr, offset, limit)
