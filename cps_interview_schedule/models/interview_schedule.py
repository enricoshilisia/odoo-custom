from datetime import datetime, timedelta
from odoo import models, fields, api
from odoo.exceptions import UserError


def _float_to_hm(f):
    """9.5 -> (9, 30)"""
    h = int(f)
    m = int(round((f - h) * 60))
    return h, m


def _fmt_slot(f):
    """9.5 -> '9:30 AM'"""
    h, m = _float_to_hm(f)
    ampm = 'AM' if h < 12 else 'PM'
    h12 = h % 12
    if h12 == 0:
        h12 = 12
    return '%d:%02d %s' % (h12, m, ampm)


class CpsInterviewSchedule(models.Model):
    _name = 'cps.interview.schedule'
    _description = 'Interview Schedule Configuration'
    _inherit = ['mail.thread']

    session_id = fields.Many2one(
        'cps.interview.session', string='Session',
        required=True, ondelete='cascade')
    name = fields.Char(string='Name', compute='_compute_name', store=True)

    date_start = fields.Date(string='First Day', required=True, tracking=True)
    date_end = fields.Date(string='Last Day', required=True, tracking=True)
    day_start_time = fields.Float(
        string='Daily Start', default=9.5, tracking=True,
        help='24h decimal, e.g. 9.5 = 9:30 AM')
    day_end_time = fields.Float(
        string='Daily End', default=16.5, tracking=True,
        help='24h decimal, e.g. 16.5 = 4:30 PM')
    slot_duration = fields.Integer(
        string='Slot Duration (min)', default=60, tracking=True)
    gap_between_slots = fields.Integer(
        string='Gap Between Slots (min)', default=15, tracking=True,
        help='Short pause after each interview for panel notes and candidate transition.')
    break_start = fields.Float(string='Lunch Start', default=13.0, tracking=True)
    break_end = fields.Float(string='Lunch End', default=14.0, tracking=True)
    max_per_day = fields.Integer(string='Max Interviews / Day', default=6, tracking=True)
    location = fields.Char(
        string='Location',
        default='TRV Towers, 10th Floor, Ngara Road, Nairobi')

    slot_ids = fields.One2many('cps.interview.slot', 'schedule_id', string='Slots')
    auto_send_date = fields.Date(
        string='Auto-send Invitations On', tracking=True,
        help='If set, invitations are sent automatically on this date. Leave empty to send manually.')
    invitations_sent = fields.Boolean(string='Invitations Sent', default=False)
    send_reminders = fields.Boolean(string='Send 24h Reminders', default=True)
    slot_count = fields.Integer(compute='_compute_counts')
    assigned_count = fields.Integer(compute='_compute_counts')

    @api.depends('session_id', 'session_id.name')
    def _compute_name(self):
        for r in self:
            r.name = 'Schedule for %s' % (r.session_id.name or 'Interview')

    @api.depends('slot_ids', 'slot_ids.applicant_id')
    def _compute_counts(self):
        for r in self:
            r.slot_count = len(r.slot_ids)
            r.assigned_count = len(r.slot_ids.filtered(lambda s: s.applicant_id))

    # -------------------------------------------------------------------------
    # Slot generation
    # -------------------------------------------------------------------------
    def action_generate_slots(self):
        self.ensure_one()
        if self.date_end < self.date_start:
            raise UserError('Last day cannot be before first day.')
        if self.day_end_time <= self.day_start_time:
            raise UserError('Daily end time must be after start time.')

        # clear only UNASSIGNED existing slots (keep manual assignments if regenerating)
        self.slot_ids.filtered(lambda s: not s.applicant_id).unlink()

        Slot = self.env['cps.interview.slot']
        dur = timedelta(minutes=self.slot_duration)
        gap = timedelta(minutes=self.gap_between_slots)

        # collect already-assigned (date,start) to avoid duplicates on regenerate
        taken = {(s.date, round(s.start_time, 4)) for s in self.slot_ids}

        day = self.date_start
        created = 0
        while day <= self.date_end:
            count_today = 0
            # walk the day in slot+gap increments
            cursor = self._float_to_dt(day, self.day_start_time)
            day_end = self._float_to_dt(day, self.day_end_time)
            b_start = self._float_to_dt(day, self.break_start)
            b_end = self._float_to_dt(day, self.break_end)

            while cursor + dur <= day_end and count_today < self.max_per_day:
                slot_end = cursor + dur
                # skip if this slot overlaps the lunch break -> jump to break end
                if cursor < b_end and slot_end > b_start:
                    cursor = b_end
                    continue
                start_f = self._dt_to_float(cursor)
                if (day, round(start_f, 4)) not in taken:
                    Slot.create({
                        'schedule_id': self.id,
                        'date': day,
                        'start_time': start_f,
                        'end_time': self._dt_to_float(slot_end),
                    })
                    created += 1
                count_today += 1
                cursor = slot_end + gap

            day += timedelta(days=1)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Slots Generated',
                'message': '%d new slot(s) created.' % created,
                'type': 'success',
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }

    def _float_to_dt(self, day, f):
        h, m = _float_to_hm(f)
        return datetime.combine(day, datetime.min.time()) + timedelta(hours=h, minutes=m)

    def _dt_to_float(self, dt):
        return dt.hour + dt.minute / 60.0

    # -------------------------------------------------------------------------
    # Auto-fill by score (HR adjusts after)
    # -------------------------------------------------------------------------
    def action_autofill_by_score(self):
        self.ensure_one()
        open_slots = self.slot_ids.filtered(lambda s: not s.applicant_id).sorted(
            key=lambda s: (s.date, s.start_time))
        if not open_slots:
            raise UserError('No open slots. Generate slots first.')

        # candidates in the session not already assigned to a slot here
        assigned = self.slot_ids.mapped('applicant_id')
        candidates = self.session_id.applicant_ids - assigned
        # sort by auto score desc (fallback 0)
        candidates = candidates.sorted(
            key=lambda a: getattr(a, 'cps_auto_score', 0) or 0, reverse=True)

        filled = 0
        for slot, applicant in zip(open_slots, candidates):
            slot.applicant_id = applicant.id
            slot.state = 'assigned'
            filled += 1

        leftover = len(candidates) - filled
        msg = '%d candidate(s) placed by score.' % filled
        if leftover > 0:
            msg += ' %d candidate(s) still need slots (not enough slots).' % leftover
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': 'Auto-fill Complete', 'message': msg,
                       'type': 'success' if leftover == 0 else 'warning'},
        }

    # -------------------------------------------------------------------------
    # Send invitations for all assigned, not-yet-invited slots
    # -------------------------------------------------------------------------
    def action_send_invitations(self):
        self.ensure_one()
        to_send = self.slot_ids.filtered(
            lambda s: s.applicant_id and s.state == 'assigned')
        if not to_send:
            raise UserError('No assigned slots waiting to be invited.')
        # Panelists must be set — they receive the calendar invites.
        if not self.session_id.panelist_ids:
            raise UserError(
                'No panelists are set on this session. Add panelists first so the '
                'calendar invitations can be sent to them.')
        # 1. Email candidates their individual slot
        sent = 0
        for slot in to_send:
            if slot._send_invite():
                slot.state = 'invited'
                sent += 1
        # 2. Create ONE panel calendar event per interview day (panelists invited)
        days_done = self._create_panel_day_events()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': 'Invitations Sent',
                       'message': '%d candidate invitation(s) sent; %d panel day event(s) created.'
                                  % (sent, days_done),
                       'type': 'success'},
        }

    def _create_panel_day_events(self):
        """One Outlook event per interview day, covering that day, inviting panelists.
        The day's FIRST slot holds the event id."""
        self.ensure_one()
        graph = self.env['cps.graph.service']
        if not graph._is_configured():
            raise UserError('Microsoft Graph is not configured (Settings > CPS Graph).')
        organizer = graph._get_organizer_upn()

        # group assigned slots by date
        by_day = {}
        for slot in self.slot_ids.filtered('applicant_id').sorted(
                key=lambda s: (s.date, s.start_time)):
            by_day.setdefault(slot.date, []).append(slot)

        # panelist attendees (from the session)
        attendees = []
        seen = set()
        for user in self.session_id.panelist_ids:
            email = (user.email or user.login or '').strip().lower()
            if email and '@' in email and email not in seen:
                seen.add(email)
                attendees.append({'emailAddress': {'address': email, 'name': user.name or email},
                                  'type': 'required'})
        if not attendees:
            raise UserError('Panelists have no valid email addresses.')

        job = self.session_id.job_id.name or 'Interview'
        location = self.location or 'Boardroom 3, TRV Towers, 10th Floor, Ngara Road, Nairobi'
        days_done = 0

        for day, slots in by_day.items():
            first = slots[0]
            if first.calendar_event_id:
                continue  # already has this day's event
            # day time range
            day_start = min(s.start_time for s in slots)
            day_end = max(s.end_time for s in slots)
            from datetime import datetime, timedelta
            base = datetime.combine(day, datetime.min.time())
            sdt = base + timedelta(hours=int(day_start), minutes=int(round((day_start % 1)*60)))
            edt = base + timedelta(hours=int(day_end), minutes=int(round((day_end % 1)*60)))
            # branded candidate table in the body
            ICP = self.env['ir.config_parameter'].sudo()
            logo = ICP.get_param('web.base.url') + '/web/image/res.company/1/logo'
            rows = ''.join(
                ('<tr>'
                 '<td style="padding:8px 12px;border-bottom:1px solid #eee;'
                 'white-space:nowrap;font-weight:600;color:#5a8a0a;">%s</td>'
                 '<td style="padding:8px 12px;border-bottom:1px solid #eee;">%s</td>'
                 '</tr>') % (s.time_label, s.candidate_name or 'Candidate')
                for s in slots)
            body = (
                '<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;'
                'border:1px solid #e0e0e0;">'
                '<div style="background:#ffffff;padding:18px 26px;border-bottom:3px solid #7ebb0e;">'
                '<img src="%s" style="max-height:48px;max-width:220px;"/></div>'
                '<div style="background:#7ebb0e;padding:16px 26px;">'
                '<h2 style="color:#fff;margin:0;font-size:19px;">Interview Panel</h2>'
                '<p style="color:#eaf7d0;margin:4px 0 0;font-size:13px;">%s</p></div>'
                '<div style="padding:24px 26px;color:#333;font-size:14px;line-height:1.6;">'
                '<p style="margin:0 0 4px;"><strong>%s</strong></p>'
                '<p style="margin:0 0 16px;color:#666;">%s</p>'
                '<table style="width:100%%;border-collapse:collapse;font-size:14px;">'
                '<thead><tr style="background:#f5f7f2;">'
                '<th style="text-align:left;padding:8px 12px;border-bottom:2px solid #7ebb0e;">Time</th>'
                '<th style="text-align:left;padding:8px 12px;border-bottom:2px solid #7ebb0e;">Candidate</th>'
                '</tr></thead><tbody>%s</tbody></table>'
                '<div style="border-left:4px solid #f28617;background:#fdf6ee;'
                'padding:12px 16px;margin:20px 0;">'
                '<strong style="color:#f28617;">Location:</strong> %s</div>'
                '<p style="color:#888;font-size:12px;margin-top:20px;">'
                'Cloud Productivity Solutions Limited &mdash; Recruitment Panel</p>'
                '</div></div>'
                % (logo, job, job, first._day_label(), rows, location))
            payload = {
                'subject': 'Interview Panel: %s (%s)' % (job, first._day_label()),
                'body': {'contentType': 'HTML', 'content': body},
                'start': {'dateTime': sdt.strftime('%Y-%m-%dT%H:%M:%S'), 'timeZone': 'Africa/Nairobi'},
                'end': {'dateTime': edt.strftime('%Y-%m-%dT%H:%M:%S'), 'timeZone': 'Africa/Nairobi'},
                'location': {'displayName': location},
                'attendees': attendees,
                'isOnlineMeeting': False,
                'allowNewTimeProposals': False,
                'reminderMinutesBeforeStart': 60,
                'categories': ['CPS Interview'],
            }
            event = graph._request('POST', '/users/%s/events' % organizer, payload=payload)
            first.calendar_event_id = (event or {}).get('id')
            days_done += 1
        return days_done


    # -------------------------------------------------------------------------
    # Automation crons
    # -------------------------------------------------------------------------
    @api.model
    def _cron_auto_send_invitations(self):
        """Send invitations for schedules whose auto_send_date has arrived."""
        from odoo import fields as _f
        today = _f.Date.today()
        due = self.search([
            ('auto_send_date', '<=', today),
            ('invitations_sent', '=', False),
        ])
        for sched in due:
            to_send = sched.slot_ids.filtered(
                lambda s: s.applicant_id and s.state == 'assigned')
            sent = 0
            for slot in to_send:
                if slot._send_invite('invite'):
                    slot.state = 'invited'
                    sent += 1
            sched.invitations_sent = True
            sched.message_post(
                body='Auto-sent %d invitation(s) on %s.' % (sent, today))

    @api.model
    def _cron_send_day_reminders(self):
        """Remind each candidate the day before THEIR interview day."""
        from odoo import fields as _f
        from datetime import timedelta
        tomorrow = _f.Date.today() + timedelta(days=1)
        Slot = self.env['cps.interview.slot']
        due = Slot.search([
            ('date', '=', tomorrow),
            ('state', 'in', ('invited', 'confirmed')),
            ('reminder_sent', '=', False),
            ('applicant_id', '!=', False),
        ])
        for slot in due:
            if not slot.schedule_id.send_reminders:
                continue
            if slot._send_invite('reminder'):
                slot.reminder_sent = True


class CpsInterviewSlot(models.Model):
    _name = 'cps.interview.slot'
    _description = 'Interview Time Slot'
    _order = 'date, start_time'
    _inherit = ['mail.thread']

    schedule_id = fields.Many2one(
        'cps.interview.schedule', string='Schedule',
        required=True, ondelete='cascade')
    session_id = fields.Many2one(
        related='schedule_id.session_id', store=True)
    date = fields.Date(string='Date', required=True)
    start_time = fields.Float(string='Start', required=True)
    end_time = fields.Float(string='End', required=True)
    time_label = fields.Char(string='Time', compute='_compute_time_label', store=True)

    applicant_id = fields.Many2one(
        'hr.applicant', string='Candidate',
        domain="[('id','in',session_applicant_ids)]")
    session_applicant_ids = fields.Many2many(
        related='schedule_id.session_id.applicant_ids')
    candidate_name = fields.Char(
        related='applicant_id.candidate_id.partner_name', string='Name')
    candidate_email = fields.Char(
        related='applicant_id.email_from', string='Email')
    candidate_score = fields.Integer(string='Score', compute='_compute_score', store=True)

    state = fields.Selection([
        ('open', 'Open'),
        ('assigned', 'Assigned'),
        ('invited', 'Invited'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
    ], string='Status', default='open', tracking=True)

    calendar_event_id = fields.Char(string='Outlook Event ID')  # for Graph later
    reminder_sent = fields.Boolean(string='Reminder Sent', default=False)
    invited_from_other_role = fields.Boolean(
        string='Invited from Another Application',
        help='Tick if this candidate applied for a different role. Uses profile-based wording.')

    @api.depends('start_time', 'end_time')
    def _compute_time_label(self):
        for s in self:
            s.time_label = '%s - %s' % (_fmt_slot(s.start_time), _fmt_slot(s.end_time))

    @api.depends('applicant_id')
    def _compute_score(self):
        for s in self:
            s.candidate_score = getattr(s.applicant_id, 'cps_auto_score', 0) or 0

    @api.onchange('applicant_id')
    def _onchange_applicant(self):
        if self.applicant_id and self.state == 'open':
            self.state = 'assigned'

    # -------------------------------------------------------------------------
    # Email helpers
    # -------------------------------------------------------------------------
    # -------------------------------------------------------------------------
    # Outlook calendar event (reuses cps.graph.service from cps_ms_graph)
    # -------------------------------------------------------------------------
    def _slot_datetimes(self):
        """Combine date + float times into naive datetime strings for Graph."""
        self.ensure_one()
        from datetime import datetime, timedelta
        base = datetime.combine(self.date, datetime.min.time())
        start = base + timedelta(hours=int(self.start_time),
                                 minutes=int(round((self.start_time % 1) * 60)))
        end = base + timedelta(hours=int(self.end_time),
                               minutes=int(round((self.end_time % 1) * 60)))
        return start.strftime('%Y-%m-%dT%H:%M:%S'), end.strftime('%Y-%m-%dT%H:%M:%S')

    def _graph_attendee_payload(self):
        """Panelists only, as Graph event attendees."""
        self.ensure_one()
        attendees = []
        seen = set()
        for user in self.session_id.panelist_ids:
            email = (user.email or user.login or '').strip().lower()
            if not email or '@' not in email or email in seen:
                continue
            seen.add(email)
            attendees.append({
                'emailAddress': {'address': email, 'name': user.name or email},
                'type': 'required',
            })
        return attendees

    def action_create_calendar_event(self):
        from odoo.exceptions import UserError
        graph = self.env['cps.graph.service']
        if not graph._is_configured():
            raise UserError('Microsoft Graph is not configured. '
                            'Add credentials in Settings > CPS Graph.')
        organizer = graph._get_organizer_upn()
        for slot in self:
            if not slot.applicant_id:
                continue
            if slot.calendar_event_id:
                raise UserError('A calendar event already exists for %s. '
                                'Cancel it first to recreate.' % slot.candidate_name)
            attendees = slot._graph_attendee_payload()
            if not attendees:
                raise UserError('No panelists with email addresses on this session. '
                                'Add panelists before creating the calendar event.')
            start, end = slot._slot_datetimes()
            job = slot.session_id.job_id.name or 'Interview'
            payload = {
                'subject': 'Interview: %s - %s' % (slot.candidate_name or 'Candidate', job),
                'body': {'contentType': 'HTML',
                         'content': '<p>Interview panel session for <strong>%s</strong>.</p>'
                                    '<p>Candidate: %s</p>' % (job, slot.candidate_name or '')},
                'start': {'dateTime': start, 'timeZone': 'Africa/Nairobi'},
                'end': {'dateTime': end, 'timeZone': 'Africa/Nairobi'},
                'location': {'displayName': 'Boardroom 3, TRV Towers, 10th Floor, Ngara Road, Nairobi'},
                'attendees': attendees,
                'isOnlineMeeting': False,
                'allowNewTimeProposals': False,
                'reminderMinutesBeforeStart': 60,
                'categories': ['CPS Interview'],
            }
            event = graph._request('POST', '/users/%s/events' % organizer, payload=payload)
            slot.calendar_event_id = (event or {}).get('id')
            slot.message_post(
                body='Outlook calendar event created for %d panelist(s).' % len(attendees))

    def _day_label(self):
        """Monday, 8 September 2026 — computed from the real date (no manual day names)."""
        self.ensure_one()
        return self.date.strftime('%A, %-d %B %Y')

    def _build_email(self, kind='invite'):
        self.ensure_one()
        GREEN, ORANGE = '#7ebb0e', '#f28617'
        ICP = self.env['ir.config_parameter'].sudo()
        logo = ICP.get_param('web.base.url') + '/web/image/res.company/1/logo'
        job = self.session_id.job_id.name or 'the position'
        name = self.candidate_name or 'Applicant'
        day = self._day_label()
        location = self.schedule_id.location or ''

        if kind == 'reschedule':
            header_bg, header = ORANGE, 'Rescheduled Interview'
            intro = ('<p>Further to our earlier correspondence, your interview has been '
                     '<strong>rescheduled</strong>. Please disregard the previous time and '
                     'note the updated details below.</p>')
        elif kind == 'reminder':
            header_bg, header = GREEN, 'Interview Reminder'
            intro = ('<p>This is a friendly reminder of your upcoming interview for the '
                     f'position of <strong>{job}</strong>.</p>')
        else:
            header_bg, header = GREEN, 'Interview Invitation'
            if self.invited_from_other_role:
                intro = (
                    '<p>Thank you for the interest you showed in Cloud Productivity '
                    'Solutions through your recent application.</p>'
                    '<p>While your application was submitted for a different role, our '
                    'team reviewed your profile and was impressed by your background. We '
                    'believe your skills and experience align well with another '
                    f'opportunity we are currently recruiting for \u2014 the position of '
                    f'<strong>{job}</strong> \u2014 and we would be pleased to invite you '
                    'to interview with our panel for this role.</p>')
            else:
                intro = (f'<p>Thank you for your application for the position of '
                         f'<strong>{job}</strong>. We are pleased to invite you to an interview '
                         f'with our panel.</p>')

        return f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;border:1px solid #e0e0e0;">
  <div style="background:#ffffff;padding:20px 28px;border-bottom:3px solid {GREEN};">
    <img src="{logo}" style="max-height:52px;max-width:230px;">
  </div>
  <div style="background:{header_bg};padding:18px 28px;">
    <h1 style="color:#fff;margin:0;font-size:20px;">{header}</h1>
  </div>
  <div style="padding:28px;color:#333;font-size:14px;line-height:1.6;">
    <p>Dear {name},</p>
    {intro}
    <div style="border-left:4px solid {ORANGE};background:#fdf6ee;padding:16px 20px;margin:22px 0;">
      <p style="margin:0 0 10px;"><strong style="color:{ORANGE};">INTERVIEW DETAILS</strong></p>
      <p style="margin:4px 0;"><strong>Day:</strong> {day}</p>
      <p style="margin:4px 0;"><strong>Time:</strong> {self.time_label}</p>
      <p style="margin:4px 0;"><strong>Location:</strong> {location}</p>
    </div>
    <p style="background:#eaf7d0;border-radius:4px;padding:12px 16px;margin:18px 0;">
       <strong>Please note:</strong> This is a <strong>physical, in-person interview</strong>.
       Kindly plan your travel accordingly.</p>
    <p>Kindly confirm your attendance by replying to this email. Please bring your original
       academic and professional certificates and your national ID, and arrive at least
       ten (10) minutes early.</p>
    <p>We look forward to meeting you.</p>
    <p style="margin-top:24px;">Best regards,<br/>
       <strong>Human Resources</strong><br/>Cloud Productivity Solutions Limited</p>
  </div>
</div>"""

    def _send_invite(self, kind='invite'):
        self.ensure_one()
        email = self.candidate_email
        if not email:
            return False
        subj_map = {
            'invite': 'Interview Invitation - ',
            'reminder': 'Interview Reminder - ',
            'reschedule': 'Rescheduled Interview - ',
        }
        subject = subj_map.get(kind, 'Interview - ') + (self.session_id.job_id.name or '')
        mail = self.env['mail.mail'].sudo().create({
            'subject': subject,
            'email_from': 'erp@cloudproductivity-solutions.com',
            'reply_to': 'hr@cloudproductivity-solutions.com',
            'email_to': email,
            'email_cc': 'hr@cloudproductivity-solutions.com,'
                        'Lawrence.Mwiti@cloudproductivity-solutions.com,'
                        'Dismus.Kigen@cloudproductivity-solutions.com',
            'body_html': self._build_email(kind),
        })
        mail.send()
        return True

    # buttons on the slot
    def action_send_invite(self):
        for s in self.filtered(lambda x: x.applicant_id):
            if s._send_invite('invite'):
                s.state = 'invited'

    def action_send_reminder(self):
        for s in self.filtered(lambda x: x.applicant_id):
            s._send_invite('reminder')

    def action_send_reschedule(self):
        for s in self.filtered(lambda x: x.applicant_id):
            s._send_invite('reschedule')
