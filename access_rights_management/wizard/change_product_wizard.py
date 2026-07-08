from odoo import fields, models, api


class ChangeProductWizard(models.TransientModel):
    _name = 'change.product.wizard'
    _description = 'Change Product Wizard'

    product_id = fields.Many2one('product.product', string='Product', required=True)
    sale_line_id = fields.Many2one('sale.order.line', string='Sale Line',default=lambda self:self.env.context.get('sale_line_id'))
    is_subscription = fields.Boolean("Is subscription")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'default_sale_line_id' in self.env.context:
            res['sale_line_id'] = self.env.context['default_sale_line_id']
        return res

    def change_product(self):
        product_updatable = self.sale_line_id.product_updatable
        self.sale_line_id.product_updatable = True
        self.sale_line_id.product_id = self.product_id.id
        self.sale_line_id.emp_filter_domain = self.product_id.emp_filter_domain
        self.sale_line_id.product_updatable = product_updatable
