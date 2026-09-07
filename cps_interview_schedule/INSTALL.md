# CPS Interview Schedule — Install & Use

Automates interview slot scheduling and branded invitations, so HR no longer
allocates slots or writes invite emails by hand. Extends `cps_interview_scoring`.

## What it does
- HR defines a schedule (days, times, slot length, gap, lunch break, max/day).
- **Generate Slots** builds the whole grid across the days automatically.
- **Auto-fill by Score** drops candidates into slots highest-score-first; HR then adjusts.
- **Send Invitations** emails each candidate their own day/time (branded, from `erp@`).
- Per-slot **Invite / Remind / Reschedule** buttons.
- Day names come from the real date (`%A`) — no more Monday/Tuesday mistakes.
- Stores `calendar_event_id` per slot, ready for Outlook/Graph push later.

## Install

1. Copy the whole `cps_interview_schedule` folder into your custom addons dir:
   ```
   /opt/odoo/custom-addons/cps_interview_schedule
   ```

2. Set ownership (so the odoo service can read it):
   ```
   sudo chown -R odoo:odoo /opt/odoo/custom-addons/cps_interview_schedule
   ```

3. Update the app list and install (from the shell):
   ```
   sudo systemctl stop odoo18
   /opt/odoo/odoo-bin -c /opt/odoo/odoo.conf -d cps-erp -u cps_interview_scoring \
       -i cps_interview_schedule --stop-after-init 2>&1 | \
       grep -iE 'error|critical|traceback|parseerror' && echo '!! ERRORS' || echo 'INSTALL CLEAN'
   sudo systemctl start odoo18
   ```

   Or via the UI: Apps → Update Apps List → search "CPS Interview Schedule" → Install.

## If install fails on `interview_schedule_optional.xml`
That file adds a button on the session form and a menu item, referencing external
IDs (`cps_interview_scoring.view_interview_session_form` and the recruitment menu).
If those IDs differ in your setup and install errors:
1. Open `__manifest__.py`
2. Delete the line: `'views/interview_schedule_optional.xml',`
3. Reinstall. The core scheduling still works — reach it via the
   **Recruitment → Interview Schedules** menu (from the core views file).

## Use
1. **Recruitment → Interview Schedules → New** (or the button on a session).
2. Pick the session, set first/last day, daily start/end, slot duration, gap,
   lunch break, max per day, location.
3. Click **Generate Slots** → the grid appears in the Slots tab.
4. Click **Auto-fill by Score** → candidates placed highest-first. Drag/reassign
   any slot manually in the list.
5. Click **Send Invitations** → all assigned candidates emailed their slot.
6. Use per-row **Remind** / **Reschedule** as needed.

## Notes
- Times are 24h decimals: 9.5 = 9:30, 13.0 = 1:00 PM, 16.5 = 4:30 PM.
- Regenerating slots keeps already-assigned slots and only rebuilds open ones.
- Candidate score reads `hr.applicant.cps_auto_score` (your prescreening score).
- Emails send from `erp@cloudproductivity-solutions.com`, reply-to `hr@`.
