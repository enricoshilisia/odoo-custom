from odoo import http
from odoo.http import request, Response
import io
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import ColorScaleRule
from datetime import datetime
from collections import Counter


def hfill(hex_): return PatternFill("solid", start_color=hex_, end_color=hex_)
def bdr():
    s = Side(style="thin", color="CCCCCC")
    return Border(left=s, right=s, top=s, bottom=s)
def center(): return Alignment(horizontal="center", vertical="center", wrap_text=True)
def left():   return Alignment(horizontal="left",   vertical="center", wrap_text=True)


class CpsScreeningReport(http.Controller):

    @http.route('/cps/screening-report/<int:job_id>', type='http', auth='user')
    def download_screening_report(self, job_id, **kwargs):
        env = request.env
        job = env['hr.job'].browse(job_id)
        if not job.exists():
            return Response("Job not found", status=404)

        # Pull live data
        applicants = env['hr.applicant'].search([('job_id', '=', job_id)])
        survey_inputs = {
            sui.applicant_id.id: sui
            for sui in env['survey.user_input'].search([
                ('applicant_id', 'in', applicants.ids),
            ])
        }

        HEADER_BG = "1F4E79"
        CPS_BLUE  = "2680AF"
        CPS_GREEN = "7EBB0E"
        SUB_BG    = "BDD7EE"
        PASS_BG   = "E2EFDA"
        FAIL_BG   = "FFDCE1"
        PENDING   = "FFF2CC"
        LGREY     = "F2F2F2"
        WHITE     = "FFFFFF"

        wb = openpyxl.Workbook()

        # ── SHEET 1: CANDIDATE COMPARISON ────────────────────────────────────
        ws = wb.active
        ws.title = "Candidate Comparison"
        ws.freeze_panes = "A4"
        ws.sheet_view.showGridLines = False

        ws.merge_cells("A1:M1")
        ws["A1"] = f"{job.name.upper()} — PRESCREENING ANALYSIS"
        ws["A1"].font = Font(name="Arial", bold=True, size=13, color=WHITE)
        ws["A1"].fill = hfill(HEADER_BG)
        ws["A1"].alignment = center()
        ws.row_dimensions[1].height = 30

        ws.merge_cells("A2:M2")
        ws["A2"] = f"Generated: {datetime.now().strftime('%d %B %Y %H:%M')}    |    Cloud Productivity Solutions Limited    |    Total: {len(applicants)}"
        ws["A2"].font = Font(name="Arial", size=9, color="444444")
        ws["A2"].fill = hfill(SUB_BG)
        ws["A2"].alignment = center()
        ws.row_dimensions[2].height = 16

        headers = ["#", "Candidate", "Email", "Stage", "Survey Status",
                   "Auto\n(/75)", "Q3\n(/10)", "Q11\n(/5)", "Q12\n(/10)",
                   "Total\n(/100)", "Pass\n(70)", "Score %", "Recommendation"]
        ws.row_dimensions[3].height = 38
        for ci, h in enumerate(headers, 1):
            c = ws.cell(row=3, column=ci, value=h)
            c.font      = Font(name="Arial", bold=True, size=9, color=WHITE)
            c.fill      = hfill(CPS_BLUE)
            c.alignment = center()
            c.border    = bdr()

        # Sort by total score desc
        sorted_apps = sorted(applicants, key=lambda a: a.cps_total_score, reverse=True)

        for ri, app in enumerate(sorted_apps, 4):
            sui   = survey_inputs.get(app.id)
            sstate = app.cps_survey_state or 'not_sent'
            stage  = app.stage_id.name if app.stage_id else ''
            cand   = app.candidate_id
            name   = cand.partner_name or ''
            email  = cand.email_from or ''
            total  = app.cps_total_score or 0

            if sstate == 'failed':      bg = FAIL_BG
            elif sstate == 'passed':    bg = PASS_BG
            elif sstate == 'in_progress': bg = PENDING
            else:                       bg = LGREY

            row = [
                ri - 3, name, email, stage,
                sstate.replace('_', ' ').title(),
                app.cps_auto_score or 0,
                app.cps_q3_score or 0,
                app.cps_q11_score or 0,
                app.cps_q12_score or 0,
                total, 70,
                f"=J{ri}/K{ri}" if total > 0 else "—",
                app.cps_score_recommendation or '—',
            ]
            for ci, val in enumerate(row, 1):
                c = ws.cell(row=ri, column=ci, value=val)
                c.fill   = hfill(bg)
                c.border = bdr()
                c.font   = Font(name="Arial", size=9)
                if ci in (1, 6, 7, 8, 9, 10, 11):
                    c.alignment = center()
                elif ci == 12 and total > 0:
                    c.number_format = "0%"
                    c.alignment = center()
                else:
                    c.alignment = left()
            ws.row_dimensions[ri].height = 16

        col_widths = [4, 26, 28, 18, 16, 8, 7, 7, 7, 8, 7, 8, 28]
        for ci, w in enumerate(col_widths, 1):
            ws.column_dimensions[get_column_letter(ci)].width = w

        if len(sorted_apps) > 0:
            ws.conditional_formatting.add(
                f"J4:J{3+len(sorted_apps)}",
                ColorScaleRule(
                    start_type="num", start_value=0,  start_color="FF0000",
                    mid_type="num",   mid_value=70,   mid_color="FFFF00",
                    end_type="num",   end_value=100,  end_color="00B050"
                )
            )

        # ── SHEET 2: SUMMARY DASHBOARD ────────────────────────────────────────
        ws2 = wb.create_sheet("Summary Dashboard")
        ws2.sheet_view.showGridLines = False

        ws2.merge_cells("A1:F1")
        ws2["A1"] = "PRESCREENING SUMMARY DASHBOARD"
        ws2["A1"].font = Font(name="Arial", bold=True, size=13, color=WHITE)
        ws2["A1"].fill = hfill(HEADER_BG)
        ws2["A1"].alignment = center()
        ws2.row_dimensions[1].height = 28

        completed = [a for a in applicants if a.cps_survey_state in ('passed','failed','in_progress')]
        scores = [a.cps_auto_score for a in completed if a.cps_auto_score]
        avg = round(sum(scores)/len(scores), 1) if scores else 0

        kpis = [
            ("Total Applicants",        len(applicants),                                              CPS_BLUE),
            ("Completed Survey",        len(completed),                                               CPS_GREEN),
            ("Awaiting Submission",     len([a for a in applicants if a.cps_survey_state == 'sent']), "F0AD4E"),
            ("Pre-Screened\n(Pending)", len([a for a in applicants if a.stage_id.id == 10]),          "5BC0DE"),
            ("Auto-Rejected",           len([a for a in applicants if a.cps_survey_state == 'failed']),"D9534F"),
            ("Avg Auto Score\n(/75)",   avg,                                                          HEADER_BG),
        ]
        ws2.row_dimensions[2].height = 8
        for ki, (label, value, color) in enumerate(kpis, 1):
            ws2.row_dimensions[3].height = 22
            ws2.row_dimensions[4].height = 44
            lc = ws2.cell(row=3, column=ki, value=label)
            lc.font = Font(name="Arial", size=9, bold=True, color=WHITE)
            lc.fill = hfill(color)
            lc.alignment = center()
            vc = ws2.cell(row=4, column=ki, value=value)
            vc.font = Font(name="Arial", size=24, bold=True, color=color)
            vc.alignment = center()
            ws2.column_dimensions[get_column_letter(ki)].width = 20

        # Stage breakdown
        ws2.row_dimensions[6].height = 8
        ws2["A7"] = "STAGE BREAKDOWN"
        ws2.merge_cells("A7:C7")
        ws2["A7"].font = Font(name="Arial", bold=True, size=10, color=WHITE)
        ws2["A7"].fill = hfill(CPS_BLUE)
        ws2["A7"].alignment = center()
        for ci, h in enumerate(["Stage","Count","% of Total"], 1):
            c = ws2.cell(row=8, column=ci, value=h)
            c.font = Font(name="Arial", bold=True, size=9, color=WHITE)
            c.fill = hfill(HEADER_BG)
            c.alignment = center()
            c.border = bdr()

        stage_counts = Counter(a.stage_id.name for a in applicants)
        ri = 9
        for stage, cnt in sorted(stage_counts.items(), key=lambda x: -x[1]):
            ws2.cell(row=ri, column=1, value=stage).border = bdr()
            ws2.cell(row=ri, column=1).font = Font(name="Arial", size=9)
            ws2.cell(row=ri, column=1).alignment = left()
            ws2.cell(row=ri, column=2, value=cnt).border = bdr()
            ws2.cell(row=ri, column=2).alignment = center()
            ws2.cell(row=ri, column=3, value=f"=B{ri}/{len(applicants)}").border = bdr()
            ws2.cell(row=ri, column=3).number_format = "0%"
            ws2.cell(row=ri, column=3).alignment = center()
            ri += 1
        ws2.column_dimensions["A"].width = 22
        ws2.column_dimensions["B"].width = 10
        ws2.column_dimensions["C"].width = 14

        # Score distribution
        ws2["E7"] = "SCORE DISTRIBUTION"
        ws2.merge_cells("E7:F7")
        ws2["E7"].font = Font(name="Arial", bold=True, size=10, color=WHITE)
        ws2["E7"].fill = hfill(CPS_BLUE)
        ws2["E7"].alignment = center()
        for ci, h in enumerate(["Score Range","Count"], 1):
            c = ws2.cell(row=8, column=4+ci, value=h)
            c.font = Font(name="Arial", bold=True, size=9, color=WHITE)
            c.fill = hfill(HEADER_BG)
            c.alignment = center()
            c.border = bdr()

        brackets = [
            ("90–100 (Highly Recommended)", [a for a in applicants if a.cps_total_score >= 90]),
            ("80–89  (Recommended)",        [a for a in applicants if 80 <= a.cps_total_score < 90]),
            ("70–79  (Consider)",           [a for a in applicants if 70 <= a.cps_total_score < 80]),
            ("50–69  (Below Pass)",         [a for a in applicants if 50 <= a.cps_total_score < 70]),
            ("1–49   (Fail)",               [a for a in applicants if 0 < a.cps_total_score < 50]),
            ("Not yet submitted",           [a for a in applicants if a.cps_total_score == 0]),
        ]
        for bi, (label, items) in enumerate(brackets):
            r = 9 + bi
            ws2.cell(row=r, column=5, value=label).border = bdr()
            ws2.cell(row=r, column=5).font = Font(name="Arial", size=9)
            ws2.cell(row=r, column=5).alignment = left()
            ws2.cell(row=r, column=6, value=len(items)).border = bdr()
            ws2.cell(row=r, column=6).alignment = center()
        ws2.column_dimensions["E"].width = 28
        ws2.column_dimensions["F"].width = 10

        # ── STREAM FILE ───────────────────────────────────────────────────────
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        filename = f"CPS_Screening_{job.name.replace(' ','_')}_{datetime.now().strftime('%Y%m%d')}.xlsx"

        return request.make_response(
            buf.read(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', f'attachment; filename="{filename}"'),
            ]
        )
