# -*- coding: utf-8 -*-

from odoo import fields, api, models


class GamificationGoal(models.Model):
    _inherit = "gamification.goal"

    global_quality_score = fields.Float('Global Quality Score', aggregator = 'avg')
    quality_score_message = fields.Html('Quality Score Info')
    total_bonus = fields.Float('Total Bonus')
