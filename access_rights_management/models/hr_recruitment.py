from odoo import models, fields, api, _


class HrApplicant(models.Model):
    _inherit = "hr.applicant"

    def action_makeMeeting(self):
        if self.env.user.has_group('access_rights_management.role_recruiter') or self.env.user.has_group(
                'access_rights_management.role_administrative_responsible') or self.env.user.has_group(
                'access_rights_management.role_hr') or self.env.user.has_group(
                'access_rights_management.role_hr_responsible'):
            res = super(HrApplicant, self.sudo()).action_makeMeeting()
            for rec in self:
                if rec.partner_id:
                    rec.partner_id.sudo().write({'is_applicant': True})
            return res
        else:
            return super(HrApplicant, self).action_makeMeeting()

    def _inverse_partner_email(self):
        if self.env.user.has_group('access_rights_management.role_recruiter') or self.env.user.has_group(
                'access_rights_management.role_administrative_responsible') or self.env.user.has_group(
                'access_rights_management.role_hr') or self.env.user.has_group(
                'access_rights_management.role_hr_responsible'):
            return super(HrApplicant, self.sudo())._inverse_partner_email()
        else:
            return super(HrApplicant, self)._inverse_partner_email()

    def _inverse_partner_phone(self):
        if self.env.user.has_group('access_rights_management.role_recruiter') or self.env.user.has_group(
                'access_rights_management.role_administrative_responsible') or self.env.user.has_group(
                'access_rights_management.role_hr') or self.env.user.has_group(
                'access_rights_management.role_hr_responsible'):
            return super(HrApplicant, self.sudo())._inverse_partner_phone()
        else:
            return super(HrApplicant, self)._inverse_partner_phone()

    def _inverse_partner_mobile(self):
        if self.env.user.has_group('access_rights_management.role_recruiter') or self.env.user.has_group(
                'access_rights_management.role_administrative_responsible') or self.env.user.has_group(
                'access_rights_management.role_hr') or self.env.user.has_group(
                'access_rights_management.role_hr_responsible'):
            return super(HrApplicant, self.sudo())._inverse_partner_mobile()
        else:
            return super(HrApplicant, self)._inverse_partner_mobile()


class HrApplicant(models.Model):
    _inherit = "hr.applicant"

    def _inverse_partner_email(self):
        if self.env.user.has_group('access_rights_management.role_recruiter') or self.env.user.has_group(
                'access_rights_management.role_administrative_responsible') or self.env.user.has_group(
                'access_rights_management.role_hr') or self.env.user.has_group(
                'access_rights_management.role_hr_responsible'):
            return super(HrApplicant, self.sudo())._inverse_partner_email()
        else:
            return super(HrApplicant, self)._inverse_partner_email()


