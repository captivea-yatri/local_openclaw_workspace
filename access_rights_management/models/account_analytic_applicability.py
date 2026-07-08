import re

from odoo import _, fields, models, api


class AccountAnalyticApplicability(models.Model):
    _inherit = 'account.analytic.applicability'

    def _get_score(self, **kwargs):
        score = super(AccountAnalyticApplicability, self.with_company(self.company_id))._get_score(**kwargs)
        return score