from odoo import models, fields


class SurveyQuestionAnswerExt(models.Model):
    _inherit = 'survey.question.answer'

    cps_is_knockout = fields.Boolean(
        string='Knockout Answer',
        default=False,
        help='If the candidate selects this answer, they are automatically '
             'disqualified regardless of their total score.',
    )
    cps_knockout_reason = fields.Char(
        string='Knockout Reason',
        help='Reason shown in the chatter and HR email when this answer '
             'triggers disqualification. Be specific and clear.',
    )


class SurveyAnswerCountExclude(models.Model):
    _inherit = 'survey.question.answer'

    cps_exclude_from_count = fields.Boolean(
        string='Exclude from Count',
        default=False,
        help='Do not count this option as a selection in count-based scoring. '
             'Use for "None of the above" / "I cannot provide proof" options.',
    )
