from odoo import models, fields


PHASE_SELECTION = [
    ('preboarding', 'Pre-Boarding'),
    ('phase1', 'Phase 1: Foundation (Days 1–30)'),
    ('phase2', 'Phase 2: Assessment (Days 31–60)'),
    ('phase3', 'Phase 3: Execution (Days 61–90)'),
]

ASSIGNEE_ROLE = [
    ('employee', 'New Employee'),
    ('hr', 'HR Admin'),
    ('it', 'IT / Operations'),
    ('line_manager', 'Line Manager'),
    ('buddy', 'Buddy / Mentor'),
    ('ceo', 'CEO / Director'),
    ('other', 'Other'),
]


class CpsOnboardingTaskTemplate(models.Model):
    _name = 'cps.onboarding.task.template'
    _description = 'Onboarding Task Template'
    _order = 'phase, day_offset, sequence'

    template_id = fields.Many2one(
        'cps.onboarding.template',
        string='Template',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Task Title', required=True)
    description = fields.Text(string='Description / Instructions')

    phase = fields.Selection(
        PHASE_SELECTION,
        string='Phase',
        required=True,
        default='phase1',
    )
    day_offset = fields.Integer(
        string='Due By (Day #)',
        required=True,
        default=7,
        help='Number of days from the employee start date this task is due. '
             'Use negative values for pre-boarding (e.g. -3 = 3 days before Day 1).',
    )

    assignee_role = fields.Selection(
        ASSIGNEE_ROLE,
        string='Assigned To (Role)',
        required=True,
        default='hr',
    )
    odoo_module = fields.Char(
        string='Odoo Module / Area',
        help='e.g. Employees, Appraisals, Time Off — for reference only.',
    )
    is_employee_visible = fields.Boolean(
        string='Visible to Employee',
        default=True,
        help='If checked, the employee can see and tick this task on their portal.',
    )
    requires_document = fields.Boolean(
        string='Requires Document Upload',
        default=False,
        help='If checked, the employee can upload a file when completing this task.',
    )
    send_reminder = fields.Boolean(
        string='Send Email Reminder',
        default=True,
        help='Send an automated reminder email when this task becomes due.',
    )
