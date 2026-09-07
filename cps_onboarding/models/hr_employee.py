from odoo import models, fields, api


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    onboarding_plan_ids = fields.One2many(
        'cps.onboarding.plan',
        'employee_id',
        string='Onboarding Plans',
    )
    active_plan_id = fields.Many2one(
        'cps.onboarding.plan',
        string='Active Onboarding Plan',
        compute='_compute_active_plan',
    )
    onboarding_progress = fields.Integer(
        string='Onboarding Progress %',
        compute='_compute_active_plan',
    )
    onboarding_health = fields.Selection([
        ('green', 'On Track'),
        ('amber', 'At Risk'),
        ('red', 'Behind'),
        ('complete', 'Complete'),
    ], string='Onboarding Health', compute='_compute_active_plan')

    @api.depends('onboarding_plan_ids', 'onboarding_plan_ids.state')
    def _compute_active_plan(self):
        for emp in self:
            active = emp.onboarding_plan_ids.filtered(
                lambda p: p.state == 'active'
            )
            plan = active[0] if active else False
            emp.active_plan_id = plan
            emp.onboarding_progress = plan.progress_pct if plan else 0
            emp.onboarding_health = plan.health if plan else False

    def action_view_onboarding(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'cps.onboarding.plan',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
            'target': 'current',
        }
