from odoo import models, fields, api, _
from odoo.tools.float_utils import float_round
from datetime import timedelta, time


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _compute_sales_count(self):
        r = {}
        self.sales_count = 0
        if self.env.user.has_group('sales_team.group_sale_salesman') or self.env.user.has_group(
                'access_rights_management.role_management_control') or self.env.user.has_group(
            'access_rights_management.role_administrative_responsible') or self.env.user.has_group(
            'access_rights_management.role_administrative') or self.env.user.has_group(
            'access_rights_management.role_vps') or self.env.user.has_group(
            'access_rights_management.role_cfo'):
            date_from = fields.Datetime.to_string(fields.datetime.combine(fields.datetime.now() - timedelta(days=365),
                                                                          time.min))

            done_states = self.env['sale.report']._get_done_states()

            domain = [
                ('state', 'in', done_states),
                ('product_id', 'in', self.ids),
                ('date', '>=', date_from),
            ]
            for product, product_uom_qty in self.env['sale.report']._read_group(domain, ['product_id'],
                                                                                ['product_uom_qty:sum']):
                r[product.id] = product_uom_qty
            for product in self:
                if not product.id:
                    product.sales_count = 0.0
                    continue
                product.sales_count = float_round(r.get(product.id, 0), precision_rounding=product.uom_id.rounding)
            return r
        else:
            return r

# Todo:in odoo 19 check the rename module of the sale.subscription.pricing in enterprise

# class ProductTemplate(models.Model):
#     _inherit = 'product.template'
#
#     product_variable_cost = fields.Boolean(string='Cost is Variable')
#     product_subscription_pricing_ids = fields.One2many(
#         'sale.subscription.pricing', 'product_template_id', string="Custom Subscription Pricings",
#         auto_join=True, copy=False, groups='sales_team.group_sale_salesman,access_rights_management.role_vps,access_rights_management.role_sales_hot,access_rights_management.role_sales_cold,access_rights_management.role_sales_cold_team_manager,access_rights_management.role_sales_cold_team_director,access_rights_management.role_management_control,access_rights_management.role_cfo,access_rights_management.role_cfo_for_his_company,access_rights_management.role_administrative_responsible,access_rights_management.role_administrative'
#     )
