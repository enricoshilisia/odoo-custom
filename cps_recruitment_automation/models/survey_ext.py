from odoo import models, fields


class SurveySurveyExt(models.Model):
    _inherit = 'survey.survey'

    cps_score_bracket_ids = fields.One2many(
        'cps.score.bracket',
        'survey_id',
        string='Score Brackets',
    )
    cps_notify_hr_on_config = fields.Boolean(
        string='Notify HR Manager on Job Assignment',
        default=True,
        help='Send email to HR Manager when this survey is attached to a job position.',
    )
    cps_hr_manager_email = fields.Char(
        string='HR Manager Email',
        default='hr@cloudproductivity-solutions.com',
        help='Email address to notify when this survey is assigned to a job.',
    )

    def get_cps_bracket(self, score):
        """Return matching bracket for a given score."""
        self.ensure_one()
        return self.env['cps.score.bracket'].search([
            ('survey_id', '=', self.id),
            ('min_score', '<=', score),
            ('max_score', '>=', score),
        ], limit=1)

    def get_cps_manual_questions(self):
        """Return all manual questions for this survey."""
        self.ensure_one()
        return self.question_ids.filtered(lambda q: q.cps_is_manual)

    def get_cps_auto_max(self):
        """Return total possible auto score (excluding manual questions)."""
        self.ensure_one()
        total = 0
        for q in self.question_ids.filtered(lambda q: not q.cps_is_manual):
            if q.cps_max_score:
                total += q.cps_max_score
            else:
                total += sum(a.answer_score for a in q.suggested_answer_ids)
        return total
