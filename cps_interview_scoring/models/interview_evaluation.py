from odoo import models, fields, api


class CpsInterviewEvaluation(models.Model):
    _name = 'cps.interview.evaluation'
    _description = 'Candidate Final Evaluation'
    _inherit = ['mail.thread']
    _order = 'session_id, applicant_id'

    session_id = fields.Many2one(
        'cps.interview.session', string='Session',
        required=True, ondelete='cascade', tracking=True,
    )
    applicant_id = fields.Many2one(
        'hr.applicant', string='Candidate',
        required=True, tracking=True,
    )
    candidate_name = fields.Char(
        related='applicant_id.partner_name',
        string='Candidate Name', store=True,
    )

    current_salary = fields.Char(string='Current Salary', tracking=True)
    expected_salary = fields.Char(string='Expected Salary', tracking=True)
    notice_period = fields.Char(string='Notice Period', tracking=True)

    recruiter_comments = fields.Text(string='Recruiter Comments')
    panel_comments = fields.Text(string='Panel Comments')

    hr_recommendation = fields.Selection([
        ('recommend', 'Recommend to Proceed'),
        ('hold', 'Hold / Reserve'),
        ('reject', 'Do Not Proceed'),
    ], string='HR Recommendation', tracking=True)

    final_decision = fields.Selection([
        ('offer', 'Extend Offer'),
        ('reserve', 'Keep in Reserve'),
        ('decline', 'Decline'),
    ], string='Final Decision', tracking=True)
    decision_date = fields.Date(string='Decision Date', tracking=True)
    decided_by = fields.Many2one('res.users', string='Decided By', tracking=True)

    _uniq_eval = models.Constraint(
        'unique(session_id, applicant_id)',
        'An evaluation already exists for this candidate in this session.',
    )


class CpsInterviewSessionEvaluation(models.Model):
    _inherit = 'cps.interview.session'

    evaluation_ids = fields.One2many(
        'cps.interview.evaluation', 'session_id',
        string='Final Evaluations',
    )

    def action_generate_evaluations(self):
        """Create a blank evaluation row for each candidate not yet having one."""
        self.ensure_one()
        existing = self.evaluation_ids.mapped('applicant_id')
        created = 0
        for a in self.applicant_ids:
            if a not in existing:
                self.env['cps.interview.evaluation'].create({
                    'session_id': self.id,
                    'applicant_id': a.id,
                })
                created += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Evaluations Ready',
                'message': '%d evaluation row(s) created.' % created,
                'type': 'success',
            }
        }
