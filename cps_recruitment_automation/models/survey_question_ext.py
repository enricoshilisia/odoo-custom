from odoo import models, fields


class SurveyQuestionExt(models.Model):
    _inherit = 'survey.question'

    cps_max_score = fields.Integer(
        string='Max Score Cap',
        default=0,
        help='Maximum score for this question regardless of selections. '
             'Use for multi-select questions. 0 = no cap.',
    )
    cps_is_manual = fields.Boolean(
        string='Manual Scoring',
        default=False,
        help='If enabled, HR scores this question manually. '
             'Candidate text response will be shown on the applicant record.',
    )
    cps_manual_max = fields.Integer(
        string='Manual Max Marks',
        default=0,
        help='Maximum marks HR can award for this manual question.',
    )
    cps_scoring_guide = fields.Text(
        string='Scoring Guide',
        help='Instructions for HR when manually scoring this question. '
             'Shown next to the scoring field on the applicant record.',
    )
    cps_is_knockout_question = fields.Boolean(
        string='Has Knockout Answers',
        compute='_compute_has_knockout',
        store=True,
    )

    def _compute_has_knockout(self):
        for q in self:
            q.cps_is_knockout_question = any(
                a.cps_is_knockout for a in q.suggested_answer_ids
            )


class SurveyQuestionCountScoring(models.Model):
    _inherit = 'survey.question'

    cps_count_scoring = fields.Boolean(
        string='Count-Based Scoring',
        default=False,
        help='Score this multi-select question by counting how many options '
             'the candidate selects, mapped through count brackets below.',
    )
    cps_count_bracket_ids = fields.One2many(
        'cps.count.bracket', 'question_id',
        string='Count Brackets',
    )

    def get_cps_count_marks(self, count):
        """Return marks for a given selection count, 0 if no bracket matches."""
        self.ensure_one()
        bracket = self.env['cps.count.bracket'].search([
            ('question_id', '=', self.id),
            ('min_count', '<=', count),
            ('max_count', '>=', count),
        ], limit=1)
        return bracket.marks if bracket else 0
