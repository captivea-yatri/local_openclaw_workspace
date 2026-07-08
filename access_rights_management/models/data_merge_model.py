from odoo import models, fields



class DataMergeModel(models.Model):
    _inherit = 'data_merge.model'

    create_threshold = fields.Integer(string='Suggestion Threshold', default=0,
                                      help='Duplicates with a similarity below this threshold will not be suggested',
                                      groups='base.group_user')