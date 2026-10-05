import csv
import io
from datetime import datetime

from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def export_as_csv(filename: str, headers: list[str], rows: list[list]) -> HttpResponse:
    """
    Streams out a CSV file response using Python's standard csv module.
    Reuses the exact same filtered query data presented on screen.
    """
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'

    writer = csv.writer(response)
    writer.writerow(headers)
    for row in rows:
        clean_row = []
        for val in row:
            if val is None:
                clean_row.append("")
            elif isinstance(val, datetime | timezone.datetime):
                clean_row.append(val.strftime("%Y-%m-%d %H:%M"))
            elif hasattr(val, "isoformat"):
                clean_row.append(val.isoformat())
            else:
                clean_row.append(str(val))
        writer.writerow(clean_row)

    return response


def export_as_pdf(
    filename: str,
    title: str,
    organization_name: str,
    headers: list[str],
    rows: list[list],
    col_widths=None,
    orientation="portrait",
    summary_text: str = "",
) -> HttpResponse:
    """
    Generates a structured PDF report using ReportLab.

    Why ReportLab?
    - Lightweight with binary wheels on Windows without external system GTK/Pango C libraries.
    - Deterministic tabular page rendering with repeat header rows across pages.
    - Recommended standard in official Django documentation.
    """
    buffer = io.BytesIO()
    pagesize = landscape(letter) if orientation == "landscape" else letter
    doc = SimpleDocTemplate(
        buffer, pagesize=pagesize, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#1a252f"),
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#555555"),
        spaceAfter=10,
    )
    cell_style = ParagraphStyle(
        "CellText",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#222222"),
    )
    cell_header_style = ParagraphStyle(
        "CellHeader",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        fontName="Helvetica-Bold",
        textColor=colors.white,
    )

    elements = []

    # Title & Metadata
    elements.append(Paragraph(f"<b>ReliefStock</b> — {title}", title_style))
    now_str = timezone.now().strftime("%Y-%m-%d %H:%M UTC")
    elements.append(
        Paragraph(
            f"Organization: <b>{organization_name}</b> | Generated: {now_str}", subtitle_style
        )
    )

    if summary_text:
        elements.append(Paragraph(f"<b>Summary:</b> {summary_text}", subtitle_style))
        elements.append(Spacer(1, 4))

    # Table data
    table_data = []
    # Header row
    table_data.append([Paragraph(h, cell_header_style) for h in headers])

    for row in rows:
        formatted_row = []
        for val in row:
            if val is None:
                text = "—"
            elif isinstance(val, datetime | timezone.datetime):
                text = val.strftime("%Y-%m-%d %H:%M")
            elif hasattr(val, "strftime"):
                text = val.strftime("%Y-%m-%d")
            else:
                text = str(val)
            formatted_row.append(Paragraph(text, cell_style))
        table_data.append(formatted_row)

    report_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    report_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
                ("TOPPADDING", (0, 0), (-1, 0), 5),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fbfbfb")]),
                ("TOPPADDING", (0, 1), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            ]
        )
    )

    elements.append(report_table)

    doc.build(elements)
    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}.pdf"'
    return response
