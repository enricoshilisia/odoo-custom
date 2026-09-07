from odoo import models, fields, api, _


class CpsOnboardingTask(models.Model):
    _name = 'cps.onboarding.task'
    _description = 'Onboarding Task'
    _order = 'phase, due_date, id'

    plan_id = fields.Many2one(
        'cps.onboarding.plan',
        string='Plan',
        required=True,
        ondelete='cascade',
    )
    name = fields.Char(string='Task', required=True)
    description = fields.Text(string='Instructions')

    phase = fields.Selection([
        ('preboarding', 'Pre-Boarding'),
        ('phase1', 'Phase 1: Foundation (Days 1–30)'),
        ('phase2', 'Phase 2: Assessment (Days 31–60)'),
        ('phase3', 'Phase 3: Execution (Days 61–90)'),
    ], string='Phase', required=True, default='phase1')

    state = fields.Selection([
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('overdue', 'Overdue'),
        ('skipped', 'Skipped'),
    ], string='Status', default='pending')

    due_date = fields.Date(string='Due Date')
    completed_date = fields.Date(string='Completed On', readonly=True)

    assignee_role = fields.Selection([
        ('employee', 'New Employee'),
        ('hr', 'HR Admin'),
        ('it', 'IT / Operations'),
        ('line_manager', 'Line Manager'),
        ('buddy', 'Buddy / Mentor'),
        ('ceo', 'CEO / Director'),
        ('other', 'Other'),
    ], string='Assigned To (Role)')

    assigned_user_id = fields.Many2one(
        'res.users',
        string='Assigned To',
    )
    odoo_module = fields.Char(string='Odoo Module / Area')
    is_employee_visible = fields.Boolean(string='Visible to Employee', default=True)
    requires_document = fields.Boolean(string='Requires Upload', default=False)
    send_reminder = fields.Boolean(string='Send Reminder', default=True)

    # Document upload (binary stored on the task)
    attached_document = fields.Binary(string='Uploaded Document')
    attached_document_filename = fields.Char(string='Filename')

    completion_note = fields.Text(string='Completion Note')

    is_overdue = fields.Boolean(
        string='Overdue',
        compute='_compute_is_overdue',
    )

    @api.depends('due_date', 'state')
    def _compute_is_overdue(self):
        today = fields.Date.today()
        for rec in self:
            rec.is_overdue = (
                rec.state not in ('done', 'skipped') and
                bool(rec.due_date) and
                rec.due_date < today
            )

    def action_mark_done(self):
        for rec in self:
            rec.write({
                'state': 'done',
                'completed_date': fields.Date.today(),
            })
            rec.plan_id._compute_progress()

    def action_mark_in_progress(self):
        for rec in self:
            if rec.state == 'pending':
                rec.state = 'in_progress'

    def action_mark_pending(self):
        for rec in self:
            rec.write({
                'state': 'pending',
                'completed_date': False,
            })

    def action_skip(self):
        for rec in self:
            rec.state = 'skipped'

    def _send_reminder_email(self):
        self.ensure_one()
        template = self.env.ref(
            'cps_onboarding.email_template_task_reminder',
            raise_if_not_found=False,
        )
        if template and self.assigned_user_id:
            template.send_mail(self.id, force_send=True)
