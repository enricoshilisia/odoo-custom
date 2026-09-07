import base64
from odoo import http, fields, _
from odoo.http import request


class OnboardingPortal(http.Controller):

    @http.route('/onboarding/<string:token>', type='http', auth='public', website=True)
    def onboarding_page(self, token, **kwargs):
        Plan = request.env['cps.onboarding.plan'].sudo()
        plan = Plan.search([('portal_token', '=', token)], limit=1)

        if not plan:
            return request.render('cps_onboarding.portal_invalid', {})

        if plan.state == 'cancelled':
            return request.render('cps_onboarding.portal_cancelled', {})

        tasks = plan.task_ids.filtered(
            lambda t: t.is_employee_visible
        ).sorted(lambda t: (t.phase, t.due_date or fields.Date.today()))

        phase_map = {
            'preboarding': 'Pre-Boarding',
            'phase1': 'Phase 1: Foundation (Days 1–30)',
            'phase2': 'Phase 2: Assessment (Days 31–60)',
            'phase3': 'Phase 3: Execution (Days 61–90)',
        }
        phase_order = ['preboarding', 'phase1', 'phase2', 'phase3']

        phases = []
        for phase_key in phase_order:
            phase_tasks = tasks.filtered(lambda t: t.phase == phase_key)
            if phase_tasks:
                phases.append({
                    'key': phase_key,
                    'label': phase_map[phase_key],
                    'tasks': phase_tasks,
                    'done': len(phase_tasks.filtered(lambda t: t.state == 'done')),
                    'total': len(phase_tasks),
                })

        return request.render('cps_onboarding.portal_main', {
            'plan': plan,
            'phases': phases,
            'token': token,
        })

    def _task_is_employee_owned(self, task):
        return task.assignee_role == 'employee'

    @http.route('/onboarding/<string:token>/task/<int:task_id>/done',
                type='http', auth='public', website=True, methods=['POST'], csrf=True)
    def mark_task_done(self, token, task_id, **kwargs):
        Plan = request.env['cps.onboarding.plan'].sudo()
        plan = Plan.search([('portal_token', '=', token)], limit=1)

        if not plan or plan.state not in ('active', 'draft'):
            return request.redirect('/onboarding/%s' % token)

        task = request.env['cps.onboarding.task'].sudo().search([
            ('id', '=', task_id),
            ('plan_id', '=', plan.id),
            ('is_employee_visible', '=', True),
            ('assignee_role', '=', 'employee'),
        ], limit=1)

        if not task:
            return request.redirect('/onboarding/%s' % token)

        vals = {
            'state': 'done',
            'completed_date': fields.Date.today(),
            'completion_note': kwargs.get('completion_note', ''),
        }

        # Handle file upload
        upload = kwargs.get('document_upload')
        if upload and hasattr(upload, 'read'):
            file_data = upload.read()
            if file_data:
                vals['attached_document'] = base64.b64encode(file_data)
                vals['attached_document_filename'] = upload.filename

        task.write(vals)
        return request.redirect('/onboarding/%s' % token)

    @http.route('/onboarding/<string:token>/task/<int:task_id>/undo',
                type='http', auth='public', website=True, methods=['POST'], csrf=True)
    def undo_task(self, token, task_id, **kwargs):
        Plan = request.env['cps.onboarding.plan'].sudo()
        plan = Plan.search([('portal_token', '=', token)], limit=1)

        if not plan or plan.state not in ('active', 'draft'):
            return request.redirect('/onboarding/%s' % token)

        task = request.env['cps.onboarding.task'].sudo().search([
            ('id', '=', task_id),
            ('plan_id', '=', plan.id),
            ('is_employee_visible', '=', True),
            ('assignee_role', '=', 'employee'),
        ], limit=1)

        if task and task.state == 'done':
            task.write({'state': 'pending', 'completed_date': False})

        return request.redirect('/onboarding/%s' % token)
