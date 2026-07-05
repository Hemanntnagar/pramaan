"""
pdf_report.py — turns a verified case record into a clean, submittable PDF.

Uses a bundled DejaVu Sans (app/fonts/) rather than reportlab's built-in
Helvetica/Times, because the rupee sign (\u20b9) is not in the base-14 PDF
fonts and silently renders as a solid black box otherwise — confirmed by
actually rendering a test page and looking at it, not assumed.
"""

from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether,
)

FONT_DIR = Path(__file__).resolve().parent / "fonts"
pdfmetrics.registerFont(TTFont("DejaVuSans", str(FONT_DIR / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))

INK = colors.HexColor("#1C2B4A")
INK_SOFT = colors.HexColor("#3B4D72")
PAPER = colors.HexColor("#F1ECDF")
SEAL = colors.HexColor("#9E2B25")
VERIFIED = colors.HexColor("#2E6E49")
AMBER = colors.HexColor("#A8731B")
LOW = colors.HexColor("#6E7F2E")

VERDICT_COLORS = {
    "verified": (VERIFIED, colors.HexColor("#E1EFE6")),
    "low": (LOW, colors.HexColor("#EFF3DD")),
    "medium": (AMBER, colors.HexColor("#F6E8CC")),
    "high": (SEAL, colors.HexColor("#F5DCDA")),
}

FLAG_COLORS = {
    "high": (SEAL, colors.HexColor("#FBEFED")),
    "medium": (AMBER, colors.HexColor("#FBF1E2")),
    "low": (LOW, colors.HexColor("#F4F6E8")),
}


def _styles():
    return {
        "brand": ParagraphStyle("brand", fontName="DejaVuSans-Bold", fontSize=18, textColor=INK, leading=22),
        "tagline": ParagraphStyle("tagline", fontName="DejaVuSans", fontSize=9, textColor=INK_SOFT, leading=12),
        "meta_label": ParagraphStyle("meta_label", fontName="DejaVuSans", fontSize=9, textColor=INK_SOFT, leading=13),
        "h2": ParagraphStyle("h2", fontName="DejaVuSans-Bold", fontSize=14, textColor=INK, spaceBefore=14, spaceAfter=6),
        "h3": ParagraphStyle("h3", fontName="DejaVuSans-Bold", fontSize=11, textColor=INK, spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("body", fontName="DejaVuSans", fontSize=10, textColor=INK, leading=14),
        "body_soft": ParagraphStyle("body_soft", fontName="DejaVuSans", fontSize=9.5, textColor=INK_SOFT, leading=13),
        "verdict_title": ParagraphStyle("verdict_title", fontName="DejaVuSans-Bold", fontSize=15, leading=18),
        "verdict_score": ParagraphStyle("verdict_score", fontName="DejaVuSans", fontSize=9.5, leading=12),
        "flag_severity": ParagraphStyle("flag_severity", fontName="DejaVuSans-Bold", fontSize=8, leading=10),
        "flag_text": ParagraphStyle("flag_text", fontName="DejaVuSans", fontSize=9.5, leading=13),
        "footer": ParagraphStyle("footer", fontName="DejaVuSans", fontSize=8, textColor=INK_SOFT, leading=11),
        "table_head": ParagraphStyle("table_head", fontName="DejaVuSans-Bold", fontSize=8.5, textColor=INK_SOFT),
        "table_cell": ParagraphStyle("table_cell", fontName="DejaVuSans", fontSize=9.5, textColor=INK),
    }


def _money(v) -> str:
    """Rs. prefix, not the unicode glyph the web app uses — see module docstring."""
    try:
        return f"Rs. {float(v):,.0f}"
    except (TypeError, ValueError):
        return "Rs. 0"


def build_pdf(case: dict) -> bytes:
    s = _styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=18 * mm, bottomMargin=16 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
        title=f"Pramaan audit report — {case.get('case_no','')}",
    )
    story = []

    # ---------- header ----------
    header_tbl = Table(
        [[
            Paragraph("PRAMAAN", s["brand"]),
            Paragraph(
                f"Case file no. <b>{case.get('case_no','—')}</b><br/>Generated {case.get('ran_at','—')}",
                s["meta_label"],
            ),
        ]],
        colWidths=[100 * mm, None],
    )
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    story.append(header_tbl)
    story.append(Paragraph("EPR audit verification report — environmental compliance", s["tagline"]))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1.2, color=SEAL))
    story.append(Spacer(1, 14))

    # ---------- case details + verdict stamp side by side ----------
    fg, bg = VERDICT_COLORS.get(case.get("verdict_class", "low"), VERDICT_COLORS["low"])
    verdict_block = Table(
        [[Paragraph(case.get("verdict", "—"), ParagraphStyle("v", parent=s["verdict_title"], textColor=fg))],
         [Paragraph(f"Risk score: {case.get('score', 0)}  (0 clean &middot; 1&ndash;3 low &middot; 4&ndash;7 medium &middot; 8+ high)",
                    ParagraphStyle("vs", parent=s["verdict_score"], textColor=fg))]],
        colWidths=[78 * mm],
    )
    verdict_block.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 1, fg),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))

    details_rows = [
        ["Producer / facility", case.get("name", "—")],
        ["Reporting period", case.get("period") or "—"],
        ["Claimed quantity", f"{case.get('claimed', 0):g} kg"],
        ["Documented quantity", f"{float(case.get('doc_sum', 0)):.0f} kg"],
        ["Registered capacity", (f"{case.get('capacity', 0):g} kg/month" if case.get("capacity") else "—")],
    ]
    details_tbl = Table(
        [[Paragraph(k, s["meta_label"]), Paragraph(str(v), s["body"])] for k, v in details_rows],
        colWidths=[42 * mm, 56 * mm],
    )
    details_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    side_by_side = Table([[details_tbl, verdict_block]], colWidths=[100 * mm, 80 * mm])
    side_by_side.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(side_by_side)

    # ---------- supporting documents ----------
    story.append(Paragraph("Supporting documents", s["h2"]))
    doc_rows = [[
        Paragraph("Invoice / e-way bill no.", s["table_head"]),
        Paragraph("Date", s["table_head"]),
        Paragraph("Quantity (kg)", s["table_head"]),
        Paragraph("Rate (Rs./kg)", s["table_head"]),
    ]]
    docs = case.get("docs") or []
    if docs:
        for d in docs:
            doc_rows.append([
                Paragraph(d.get("invoice") or "—", s["table_cell"]),
                Paragraph(d.get("date") or "—", s["table_cell"]),
                Paragraph(f"{float(d.get('qty', 0) or 0):g}", s["table_cell"]),
                Paragraph(_money(d.get("rate", 0)).replace("Rs. ", ""), s["table_cell"]),
            ])
    else:
        doc_rows.append([Paragraph("No supporting documents were submitted with this case.", s["body_soft"]), "", "", ""])

    docs_tbl = Table(doc_rows, colWidths=[62 * mm, 32 * mm, 38 * mm, 38 * mm], repeatRows=1)
    docs_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PAPER),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, INK_SOFT),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, colors.HexColor("#DCD6C4")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(docs_tbl)

    # ---------- flags ----------
    story.append(Paragraph("Findings", s["h2"]))
    flags = case.get("flags") or []
    if not flags:
        story.append(Paragraph("No inconsistencies were found across the checks run on this case.",
                                ParagraphStyle("clean", parent=s["body"], textColor=VERIFIED, fontName="DejaVuSans-Bold")))
    else:
        for f in flags:
            fg2, bg2 = FLAG_COLORS.get(f.get("severity", "low"), FLAG_COLORS["low"])
            row = Table(
                [[Paragraph(f.get("severity", "").upper() + " SEVERITY", ParagraphStyle("fs", parent=s["flag_severity"], textColor=fg2)),],
                 [Paragraph(f.get("text", ""), s["flag_text"])]],
                colWidths=[160 * mm],
            )
            row.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), bg2),
                ("LINEBEFORE", (0, 0), (0, -1), 3, fg2),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]))
            story.append(row)
            story.append(Spacer(1, 6))

    # ---------- footer ----------
    footer_block = [
        Spacer(1, 16),
        HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#C9B679")),
        Spacer(1, 6),
        Paragraph(
            "This report was generated by Pramaan, an automated cross-verification tool, based on the "
            "claimed figures and supporting documents entered for this case. It is a screening aid, not "
            "a substitute for the auditor's own professional judgement, and should be read alongside the "
            "original source documents before a final determination is recorded.",
            s["footer"],
        ),
    ]
    story.append(KeepTogether(footer_block))

    doc.build(story)
    return buf.getvalue()
