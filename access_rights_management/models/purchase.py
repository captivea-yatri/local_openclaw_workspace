from odoo import models, fields


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    credit_card_no = fields.Char()


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    invoice_lines = fields.One2many('account.move.line', 'purchase_line_id', string="Bill Lines", readonly=True,
                                    copy=False, groups="purchase.group_purchase_user")
