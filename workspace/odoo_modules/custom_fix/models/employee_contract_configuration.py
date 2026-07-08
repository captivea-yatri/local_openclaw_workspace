# -*- coding: utf-8 -*-
"""Override to fix action_send_sign_requests return value.
Ensures the method returns an action dict instead of a plain boolean,
which caused the RPC test to raise `'bool' object has no attribute 'rpartition'`.
"""

from odoo import models


class EmployeeContractConfiguration(models.Model):
    _inherit = "employee.contract.configuration"

    def action_send_sign_requests(self):
        """Call the original implementation, then guarantee an action dict.
        If the original returns a boolean, replace it with a minimal window action
        pointing to the created sign.request records.
        """
        # Call super – may raise if not overridden correctly
        result = super(EmployeeContractConfiguration, self).action_send_sign_requests()
        if isinstance(result, bool):
            # Build a safe fallback action showing the related sign requests
            return {
                "type": "ir.actions.act_window",
                "name": "Sign Requests",
                "res_model": "sign.request",
                "view_mode": "tree,form",
                "domain": [("contract_config_id", "in", self.ids)],
                "target": "current",
            }
        return result
