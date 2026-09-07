from odoo import models, fields, api
from odoo.exceptions import ValidationError


class CpsScoreBracket(models.Model):
    _name = 'cps.score.bracket'
    _description = 'CPS Survey Score Bracket'
    _order = 'min_score desc'

    survey_id = fields.Many2one(
        'survey.survey',
        string='Survey',
        required=True,
        ondelete='cascade',
    )
    label = fields.Char(
        string='Label',
        required=True,
        help='e.g. Highly Recommended, Recommended, Consider, Not Recommended',
    )
    min_score = fields.Integer(string='Min Score', required=True, default=0)
    max_score = fields.Integer(string='Max Score', required=True, default=100)
    stage_id = fields.Many2one(
        'hr.recruitment.stage',
        string='Move to Stage',
        required=True,
        help='Applicant is moved to this stage when their total score falls in this bracket.',
    )
    survey_state = fields.Selection([
        ('passed',      'Passed'),
        ('failed',      'Failed'),
        ('in_progress', 'Pending Manual Review'),
    ], string='Survey Status', required=True, default='passed')
    notify_hr = fields.Boolean(
        string='Notify HR Manager',
        default=True,
        help='Send email notification to HR Manager when applicant lands in this bracket.',
    )

    @api.constrains('min_score', 'max_score')
    def _check_scores(self):
        for rec in self:
            if rec.min_score > rec.max_score:
                raise ValidationError(
                    f'Min score ({rec.min_score}) cannot be greater than '
                    f'max score ({rec.max_score}) in bracket "{rec.label}".'
                )

    def get_bracket_for_score(self, survey_id, score):
        """Return the matching bracket for a given survey and score."""
        bracket = self.search([
            ('survey_id', '=', survey_id),
            ('min_score', '<=', score),
            ('max_score', '>=', score),
        ], limit=1)
        return bracket
