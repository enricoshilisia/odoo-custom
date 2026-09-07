from odoo import models, fields, api, _
from odoo.exceptions import UserError


class CpsOnboardingTemplate(models.Model):
    _name = 'cps.onboarding.template'
    _description = 'Onboarding Plan Template'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char(
        string='Template Name',
        required=True,
        tracking=True,
        help='e.g. "HR Manager 90-Day Plan" or "Software Engineer Onboarding"',
    )
    job_id = fields.Many2one(
        'hr.job',
        string='Job Position',
        help='Optional — link to a specific job position for quick filtering.',
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
    )
    description = fields.Text(string='Description / Notes')
    active = fields.Boolean(default=True)

    task_template_ids = fields.One2many(
        'cps.onboarding.task.template',
        'template_id',
        string='Task Templates',
    )

    total_tasks = fields.Integer(
        string='Total Tasks',
        compute='_compute_counts',
    )
    total_phases = fields.Integer(
        string='Phases',
        compute='_compute_counts',
    )
    duration_days = fields.Integer(
        string='Duration (Days)',
        compute='_compute_counts',
        help='Based on the latest due-day offset across all tasks.',
    )

    @api.depends('task_template_ids', 'task_template_ids.day_offset', 'task_template_ids.phase')
    def _compute_counts(self):
        for rec in self:
            tasks = rec.task_template_ids
            rec.total_tasks = len(tasks)
            rec.total_phases = len(set(tasks.mapped('phase')))
            offsets = tasks.mapped('day_offset')
            rec.duration_days = max(offsets) if offsets else 0

    def action_duplicate(self):
        self.ensure_one()
        new = self.copy({'name': _('Copy of %s') % self.name})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'cps.onboarding.template',
            'res_id': new.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_plan(self):
        """Shortcut: open new plan form pre-filled with this template."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'cps.onboarding.plan',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_template_id': self.id,
                'default_job_id': self.job_id.id,
                'default_department_id': self.department_id.id,
            },
        }
