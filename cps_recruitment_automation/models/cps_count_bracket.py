from odoo import models, fields


class CpsCountBracket(models.Model):
    _name = 'cps.count.bracket'
    _description = 'Count-Based Scoring Bracket'
    _order = 'min_count'

    question_id = fields.Many2one(
        'survey.question', string='Question',
        required=True, ondelete='cascade',
    )
    min_count = fields.Integer(string='Min Selections', required=True)
    max_count = fields.Integer(
        string='Max Selections', required=True,
        help='Use a high number like 99 for "or more".',
    )
    marks = fields.Integer(string='Marks Awarded', required=True)
