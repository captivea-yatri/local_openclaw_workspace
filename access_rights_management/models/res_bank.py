from odoo import models

class ResBank(models.Model):
    _inherit = "res.bank"

    def write(self, vals):
        """
        If the user is a administrative responsible, while add bank account on employee he does not face any access error.
        """
        if self.env.user.has_group('access_rights_management.role_administrative_responsible'):
            return super(ResBank, self.sudo()).write(vals)
        else:
            return super(ResBank, self).write(vals)