from odoo import models, fields


class CpsInterviewQuestion(models.Model):
    _name = 'cps.interview.question'
    _description = 'Interview Question'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    session_id = fields.Many2one(
        'cps.interview.session',
        string='Session',
        required=True,
        ondelete='cascade',
    )
    name = fields.Char(string='Question', required=True)
    max_score = fields.Integer(string='Max Score', default=5)
    scoring_guide = fields.Text(
        string='Look For / Scoring Guide',
        help='Guidance shown to panelists on what to assess for this question.',
    )
