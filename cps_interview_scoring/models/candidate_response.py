from odoo import models, fields


class CpsCandidateResponse(models.Model):
    _name = 'cps.candidate.response'
    _description = 'Candidate Post-Interview Response'

    session_id = fields.Many2one(
        'cps.interview.session',
        string='Session',
        required=True,
        ondelete='cascade',
    )
    token_id = fields.Many2one(
        'cps.candidate.token',
        string='Candidate Token',
        required=True,
        ondelete='cascade',
    )
    applicant_id = fields.Many2one(
        'hr.applicant',
        string='Candidate',
        required=True,
    )

    # Passport photo
    passport_photo = fields.Binary(string='Passport Photo')
    passport_photo_filename = fields.Char(string='Photo Filename')

    # Availability
    availability = fields.Text(string='Availability Answer')

    # Emoji rating
    emoji_rating = fields.Selection([
        ('great', '😊 Great'),
        ('okay', '😐 Okay'),
        ('poor', '😞 Needs Improvement'),
    ], string='Process Rating')

    # 3 comment lines
    comment_1 = fields.Text(string='What did you enjoy most about the process?')
    comment_2 = fields.Text(string='What could we improve?')
    comment_3 = fields.Text(string='Any other feedback?')

    submitted_date = fields.Datetime(string='Submitted On', readonly=True)
