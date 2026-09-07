import uuid
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta


class CpsOnboardingPlan(models.Model):
    _name = 'cps.onboarding.plan'
    _description = 'Employee Onboarding Plan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'start_date desc'

    name = fields.Char(
        string='Plan Name',
        required=True,
        tracking=True,
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        tracking=True,
    )
    template_id = fields.Many2one(
        'cps.onboarding.template',
        string='Template Used',
        tracking=True,
    )
    job_id = fields.Many2one(
        'hr.job',
        string='Job Position',
        related='employee_id.job_id',
        store=True,
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        related='employee_id.department_id',
        store=True,
    )
    start_date = fields.Date(
        string='Start Date (Day 1)',
        required=True,
        tracking=True,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    # Assigned people (actual users, not just roles)
    line_manager_id = fields.Many2one('res.users', string='Line Manager')
    it_owner_id = fields.Many2one('res.users', string='IT / Operations Owner')
    buddy_id = fields.Many2one('res.users', string='Buddy / Mentor')
    hr_owner_id = fields.Many2one('res.users', string='HR Owner')

    task_ids = fields.One2many(
        'cps.onboarding.task',
        'plan_id',
        string='Tasks',
    )

    # Portal access token
    portal_token = fields.Char(
        string='Portal Token',
        default=lambda self: str(uuid.uuid4()),
        readonly=True,
        copy=False,
    )
    portal_url = fields.Char(
        string='Employee Portal URL',
        compute='_compute_portal_url',
    )

    # Progress stats
    total_tasks = fields.Integer(compute='_compute_progress', store=True)
    done_tasks = fields.Integer(compute='_compute_progress', store=True)
    overdue_tasks = fields.Integer(compute='_compute_progress', store=True)
    progress_pct = fields.Integer(
        string='Progress %',
        compute='_compute_progress',
        store=True,
    )
    current_phase = fields.Char(
        string='Current Phase',
        compute='_compute_progress',
        store=True,
    )
    health = fields.Selection([
        ('green', 'On Track'),
        ('amber', 'At Risk'),
        ('red', 'Behind'),
        ('complete', 'Complete'),
    ], string='Health', compute='_compute_progress', store=True)

    tasks_html_preboarding = fields.Html(
        string='Pre-Boarding Tasks',
        compute='_compute_tasks_html',
        sanitize=False,
    )
    tasks_html_phase1 = fields.Html(
        string='Phase 1 Tasks',
        compute='_compute_tasks_html',
        sanitize=False,
    )
    tasks_html_phase2 = fields.Html(
        string='Phase 2 Tasks',
        compute='_compute_tasks_html',
        sanitize=False,
    )
    tasks_html_phase3 = fields.Html(
        string='Phase 3 Tasks',
        compute='_compute_tasks_html',
        sanitize=False,
    )

    @api.depends('task_ids', 'task_ids.state', 'task_ids.name', 'task_ids.due_date',
                 'task_ids.assigned_user_id', 'task_ids.assignee_role',
                 'task_ids.completed_date', 'task_ids.phase')
    def _compute_tasks_html(self):
        today = fields.Date.today()

        phase_map = {
            'preboarding': 'tasks_html_preboarding',
            'phase1': 'tasks_html_phase1',
            'phase2': 'tasks_html_phase2',
            'phase3': 'tasks_html_phase3',
        }
        role_labels = {
            'employee': 'New Employee',
            'hr': 'HR Admin',
            'it': 'IT / Operations',
            'line_manager': 'Line Manager',
            'buddy': 'Buddy / Mentor',
            'ceo': 'CEO / Director',
            'other': 'Other',
        }
        state_styles = {
            'done': ('background:#eafaf1;color:#27ae60;', '&#10003; Done'),
            'in_progress': ('background:#fef9e7;color:#f39c12;', '&#9654; In Progress'),
            'overdue': ('background:#fdedec;color:#e74c3c;', '&#9888; Overdue'),
            'skipped': ('background:#f2f3f4;color:#aaa;', '&#187;&#187; Skipped'),
            'pending': ('background:#eaf0ff;color:#0f3460;', '&#9679; Pending'),
        }

        for rec in self:
            for phase_key, field_name in phase_map.items():
                tasks = rec.task_ids.filtered(
                    lambda t, p=phase_key: t.phase == p
                ).sorted(lambda t: t.due_date or today)

                if not tasks:
                    setattr(rec, field_name,
                        '<p style="color:#aaa;font-style:italic;padding:12px;">No tasks in this phase.</p>')
                    continue

                done = len(tasks.filtered(lambda t: t.state == 'done'))
                total = len(tasks)
                pct = int(done / total * 100) if total else 0

                overdue_count = len(tasks.filtered(
                    lambda t: t.state not in ('done', 'skipped') and t.due_date and t.due_date < today
                ))

                html = []
                html.append('<div style="font-family:Arial,sans-serif;font-size:13px;">')

                # Phase summary bar
                bar_color = '#27ae60' if pct == 100 else ('#e67e22' if overdue_count > 0 else '#0f3460')
                html.append(
                    '<div style="display:flex;align-items:center;gap:16px;'
                    'padding:12px 16px;background:#f8f9fa;border-radius:8px;margin-bottom:14px;">'
                    '<div style="flex:1;">'
                    '<div style="background:#e0e4ef;border-radius:10px;height:8px;overflow:hidden;">'
                    '<div style="width:%d%%;height:100%%;background:%s;border-radius:10px;'
                    'transition:width 0.3s;"></div></div></div>'
                    '<span style="font-weight:700;color:%s;white-space:nowrap;">%d / %d done</span>'
                    % (pct, bar_color, bar_color, done, total)
                )
                if overdue_count > 0:
                    html.append(
                        '<span style="color:#e74c3c;font-weight:600;white-space:nowrap;">'
                        '&#9888; %d overdue</span>' % overdue_count
                    )
                html.append('</div>')

                # Table
                html.append(
                    '<table style="width:100%;border-collapse:collapse;">'
                    '<thead><tr style="background:#1a1a2e;color:#fff;">'
                    '<th style="padding:10px 12px;text-align:left;font-size:12px;width:40%%;">Task</th>'
                    '<th style="padding:10px 12px;text-align:left;font-size:12px;">Assigned To</th>'
                    '<th style="padding:10px 12px;text-align:center;font-size:12px;">Due Date</th>'
                    '<th style="padding:10px 12px;text-align:center;font-size:12px;">Status</th>'
                    '<th style="padding:10px 12px;text-align:center;font-size:12px;">Completed</th>'
                    '</tr></thead><tbody>'
                )

                for i, task in enumerate(tasks):
                    bg = '#fff' if i % 2 == 0 else '#fafbff'
                    state_style, state_label = state_styles.get(
                        task.state, ('background:#eee;color:#333;', task.state)
                    )
                    is_overdue = (
                        task.state not in ('done', 'skipped') and
                        task.due_date and task.due_date < today
                    )
                    due_style = 'color:#e74c3c;font-weight:700;' if is_overdue else 'color:#333;'

                    assigned = (
                        task.assigned_user_id.name if task.assigned_user_id
                        else role_labels.get(task.assignee_role, task.assignee_role or '-')
                    )

                    html.append(
                        '<tr style="background:%s;border-bottom:1px solid #eee;">' % bg
                    )
                    # Task name — bold if overdue
                    name_style = 'font-weight:700;' if is_overdue else ''
                    done_style = 'text-decoration:line-through;color:#aaa;' if task.state == 'done' else ''
                    html.append(
                        '<td style="padding:10px 12px;font-size:13px;%s%s">%s</td>'
                        % (name_style, done_style, task.name)
                    )
                    html.append(
                        '<td style="padding:10px 12px;font-size:12px;color:#555;">%s</td>'
                        % assigned
                    )
                    html.append(
                        '<td style="padding:10px 12px;text-align:center;font-size:12px;%s">%s</td>'
                        % (due_style, task.due_date.strftime('%d %b %Y') if task.due_date else '-')
                    )
                    html.append(
                        '<td style="padding:10px 12px;text-align:center;">'
                        '<span style="padding:4px 10px;border-radius:12px;font-size:11px;'
                        'font-weight:700;%s">%s</span></td>'
                        % (state_style, state_label)
                    )
                    html.append(
                        '<td style="padding:10px 12px;text-align:center;font-size:12px;color:#666;">%s</td>'
                        % (task.completed_date.strftime('%d %b %Y') if task.completed_date else '-')
                    )
                    html.append('</tr>')

                html.append('</tbody></table>')
                html.append(
                    '<p style="font-size:11px;color:#aaa;margin-top:8px;text-align:right;">'
                    'To update task status: use the All Tasks tab or the Tasks menu.</p>'
                )
                html.append('</div>')

                setattr(rec, field_name, ''.join(html))

    @api.depends('portal_token')
    def _compute_portal_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for rec in self:
            rec.portal_url = '%s/onboarding/%s' % (base_url, rec.portal_token)

    @api.depends('task_ids', 'task_ids.state', 'task_ids.due_date', 'task_ids.phase')
    def _compute_progress(self):
        today = fields.Date.today()
        phase_order = ['preboarding', 'phase1', 'phase2', 'phase3']
        phase_labels = {
            'preboarding': 'Pre-Boarding',
            'phase1': 'Phase 1: Foundation',
            'phase2': 'Phase 2: Assessment',
            'phase3': 'Phase 3: Execution',
        }
        for rec in self:
            tasks = rec.task_ids
            total = len(tasks)
            done = len(tasks.filtered(lambda t: t.state == 'done'))
            overdue = len(tasks.filtered(
                lambda t: t.state != 'done' and t.due_date and t.due_date < today
            ))
            rec.total_tasks = total
            rec.done_tasks = done
            rec.overdue_tasks = overdue
            rec.progress_pct = int((done / total * 100)) if total else 0

            # Current phase = lowest phase that still has pending tasks
            pending = tasks.filtered(lambda t: t.state != 'done')
            if pending:
                phases = pending.mapped('phase')
                current = next((p for p in phase_order if p in phases), 'phase1')
                rec.current_phase = phase_labels.get(current, current)
            else:
                rec.current_phase = 'Complete'

            # Health
            if done == total and total > 0:
                rec.health = 'complete'
            elif overdue == 0:
                rec.health = 'green'
            elif overdue <= 2:
                rec.health = 'amber'
            else:
                rec.health = 'red'

    def action_generate_tasks(self):
        """Generate tasks from the selected template."""
        self.ensure_one()
        if not self.template_id:
            raise UserError(_('Please select a template first.'))
        if not self.start_date:
            raise UserError(_('Please set the start date first.'))
        if self.task_ids:
            raise UserError(_(
                'Tasks have already been generated for this plan. '
                'Delete existing tasks first if you want to regenerate.'
            ))

        role_user_map = {
            'hr': self.hr_owner_id,
            'line_manager': self.line_manager_id,
            'it': self.it_owner_id,
            'buddy': self.buddy_id,
            'ceo': self.line_manager_id,
            'employee': False,
            'other': False,
        }

        for tmpl in self.template_id.task_template_ids:
            due = self.start_date + timedelta(days=tmpl.day_offset)
            assigned_user = role_user_map.get(tmpl.assignee_role, False)
            self.env['cps.onboarding.task'].create({
                'plan_id': self.id,
                'name': tmpl.name,
                'description': tmpl.description,
                'phase': tmpl.phase,
                'due_date': due,
                'assignee_role': tmpl.assignee_role,
                'assigned_user_id': assigned_user.id if assigned_user else False,
                'odoo_module': tmpl.odoo_module,
                'is_employee_visible': tmpl.is_employee_visible,
                'requires_document': tmpl.requires_document,
                'send_reminder': tmpl.send_reminder,
            })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Tasks Generated'),
                'message': _('%d task(s) created from template.') % len(self.task_ids),
                'type': 'success',
            }
        }

    def action_activate(self):
        self.ensure_one()
        if not self.task_ids:
            raise UserError(_('Please generate tasks before activating the plan.'))
        self.state = 'active'
        self._send_welcome_email()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Plan Activated'),
                'message': _('Onboarding plan is now active. Welcome email sent to employee.'),
                'type': 'success',
            }
        }

    def action_complete(self):
        self.ensure_one()
        self.state = 'completed'

    def action_cancel(self):
        self.ensure_one()
        self.state = 'cancelled'

    def action_reset_draft(self):
        self.ensure_one()
        self.state = 'draft'

    def _send_welcome_email(self):
        template = self.env.ref(
            'cps_onboarding.email_template_onboarding_welcome',
            raise_if_not_found=False,
        )
        if template:
            template.send_mail(self.id, force_send=True)

    def action_send_portal_link(self):
        self.ensure_one()
        template = self.env.ref(
            'cps_onboarding.email_template_portal_link',
            raise_if_not_found=False,
        )
        if template:
            template.send_mail(self.id, force_send=True)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Link Sent'),
                'message': _('Portal link sent to %s.') % self.employee_id.name,
                'type': 'success',
            }
        }

    def action_view_report(self):
        self.ensure_one()
        return self.env.ref(
            'cps_onboarding.action_onboarding_progress_report'
        ).report_action(self)

    def action_send_overdue_reminders(self):
        """Send reminder emails for all overdue tasks."""
        self.ensure_one()
        today = fields.Date.today()
        overdue = self.task_ids.filtered(
            lambda t: t.state != 'done' and t.due_date and t.due_date < today
        )
        for task in overdue:
            task._send_reminder_email()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reminders Sent'),
                'message': _('%d reminder(s) sent for overdue tasks.') % len(overdue),
                'type': 'success',
            }
        }

    @api.model
    def _cron_send_reminders(self):
        """Scheduled action: send reminders for tasks due today."""
        today = fields.Date.today()
        tasks = self.env['cps.onboarding.task'].search([
            ('plan_id.state', '=', 'active'),
            ('state', '!=', 'done'),
            ('due_date', '=', today),
            ('send_reminder', '=', True),
        ])
        for task in tasks:
            task._send_reminder_email()

    @api.model
    def _cron_update_overdue(self):
        """Scheduled action: mark tasks as overdue."""
        today = fields.Date.today()
        tasks = self.env['cps.onboarding.task'].search([
            ('plan_id.state', '=', 'active'),
            ('state', 'in', ['pending', 'in_progress']),
            ('due_date', '<', today),
        ])
        tasks.write({'state': 'overdue'})
