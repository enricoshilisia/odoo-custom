from odoo import models, fields


class HrJob(models.Model):
    _inherit = 'hr.job'

    survey_config_ids = fields.One2many(
        'cps.recruitment.survey.config',
        'job_id',
        string='Recruitment Surveys',
    )

    def action_cps_download_screening_report(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/cps/screening-report/{self.id}',
            'target': 'new',
        }
