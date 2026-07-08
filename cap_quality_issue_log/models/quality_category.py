# -*- coding: utf-8 -*-

from odoo import fields, api, models


class QualityCategory(models.Model):
    _name = "quality.category"
    _description = "Quality Category"

    name = fields.Char('Name')
    weight = fields.Float('Weight')
    role_ids = fields.Many2many('planning.role', 'quality_category_planning_role_rel', 'category_id', 'role_id',
                                string='Project Roles')
    warning_before_penalty = fields.Boolean('Warning Before Penalty', Default=False)

    def check_role(self, employee_id, project_ids, quality_data, categ_quality_score, list_of_quality_category_id,
                   weight, quality_score):
        if self.role_ids:
            for role_id in self.role_ids:
                if role_id.is_project_manager and employee_id.user_id in project_ids.user_id:
                    self.prepare_quality_data(quality_data, categ_quality_score,
                                              list_of_quality_category_id, weight, quality_score)
                elif role_id.is_business_analyst and employee_id.user_id in project_ids.business_analyst_ids:
                    self.prepare_quality_data(quality_data, categ_quality_score,
                                              list_of_quality_category_id, weight, quality_score)
                elif role_id.is_configurator and employee_id.user_id in project_ids.configurators_ids:
                    self.prepare_quality_data(quality_data, categ_quality_score,
                                              list_of_quality_category_id, weight, quality_score)
                elif role_id.is_developer and employee_id.user_id in project_ids.developers_ids:
                    self.prepare_quality_data(quality_data, categ_quality_score,
                                              list_of_quality_category_id, weight, quality_score)
                elif role_id.is_architect and employee_id.user_id in project_ids.architect_ids:
                    self.prepare_quality_data(quality_data, categ_quality_score,
                                              list_of_quality_category_id, weight, quality_score)
        else:
            self.prepare_quality_data(quality_data, categ_quality_score, list_of_quality_category_id, weight,
                                      quality_score)

    def prepare_quality_data(self, quality_data, categ_quality_score, list_of_quality_category_id, weight,
                             quality_score):
        if quality_data:
            weight += self.weight
            quality_score += (categ_quality_score * self.weight) / 100
            if self.id not in list_of_quality_category_id:
                list_of_quality_category_id.append(self.id)
                return quality_data.append({'weight': weight, 'quality_score': quality_score,
                                            'message': str(self.name) + " : " + str(categ_quality_score) + "% / weight : " + str(weight) + "<br/>"})
            else:
                return quality_data.append({'weight': weight, 'quality_score': quality_score})
        else:
            list_of_quality_category_id.append(self.id)
            weight += self.weight
            quality_score += (categ_quality_score * self.weight) / 100
            return quality_data.append({'weight': weight, 'quality_score': quality_score,
                                        'message': str(self.name) + " : " + str(categ_quality_score) + "% / weight : " + str(weight) + "<br/>"})
