from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    SimpleDocTemplate,
)
from xml.sax.saxutils import escape


INR_PER_USD = 83.0


def _money_value(data: dict[str, Any], keys: list[str]) -> float:
    for key in keys:
        value = data.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0


def _text(value: Any, default: str = "-") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return escape(text) if text else default


def _header_footer(canvas, doc) -> None:
    page_num = canvas.getPageNumber()
    width, height = A4

    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#0f172a"))
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(doc.leftMargin, height - 32, "RoadMind AI")
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(width - doc.rightMargin, height - 30, f"Page {page_num}")
    canvas.setStrokeColor(colors.HexColor("#cbd5e1"))
    canvas.setLineWidth(0.8)
    canvas.line(doc.leftMargin, height - 38, width - doc.rightMargin, height - 38)

    canvas.setStrokeColor(colors.HexColor("#cbd5e1"))
    canvas.line(doc.leftMargin, 32, width - doc.rightMargin, 32)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(doc.leftMargin, 20, "RoadMind AI trip report")
    canvas.drawRightString(width - doc.rightMargin, 20, datetime.now().strftime("%Y-%m-%d"))
    canvas.restoreState()


def _build_section_table(title: str, rows: list[list[Any]], col_widths: list[float]) -> Table:
    data = [[title, "Details"]]
    if rows:
        data.extend(rows)
    else:
        data.append(["-", "No data provided"])

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor("#eef2ff")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEADING", (0, 0), (-1, -1), 11),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def generate_pdf_report(trip_data: dict[str, Any], output_path: str) -> dict[str, Any]:
    """Generate a professional, branded multi-page PDF report for a road trip."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.85 * inch,
        bottomMargin=0.8 * inch,
        title="RoadMind AI Road Trip Report",
        author="RoadMind AI",
    )

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="RoadMindTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=28,
            textColor=colors.HexColor("#0f172a"),
            alignment=TA_CENTER,
            spaceAfter=16,
        )
    )
    styles.add(
        ParagraphStyle(
            name="RoadMindSubtle",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#475569"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="RoadMindSection",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=10,
        )
    )

    origin = trip_data.get("origin", "-")
    destination = trip_data.get("destination", "-")
    travel_dates = trip_data.get("travel_dates") or {}
    route = trip_data.get("route") or {}
    recommendations = trip_data.get("recommendations") or {}
    budget = trip_data.get("budget") or {}

    fuel_inr = _money_value(budget, ["fuel", "fuel_inr", "fuel_cost_inr"])
    toll_inr = _money_value(budget, ["tolls", "tolls_inr", "toll_cost_inr"])
    hotel_inr = _money_value(budget, ["hotels", "hotel", "lodging", "hotel_cost_inr"])
    food_inr = _money_value(budget, ["food", "food_inr", "food_cost_inr"])
    misc_inr = _money_value(budget, ["miscellaneous", "miscellaneous_inr"])
    total_inr = _money_value(budget, ["total", "total_inr"])
    total_usd = _money_value(budget, ["total_usd"]) or round(total_inr / INR_PER_USD, 2)

    story: list[Any] = []

    # Page 1
    story.append(Spacer(1, 40))
    story.append(Paragraph("RoadMind AI", styles["RoadMindTitle"]))
    story.append(Paragraph("AI-powered Road Trip Report", styles["RoadMindSubtle"]))
    story.append(Spacer(1, 24))

    trip_summary_rows = [
        ["Route", f"{_text(origin)} → {_text(destination)}"],
        ["Travel dates", f"{_text(travel_dates.get('start'))} to {_text(travel_dates.get('end'))}"],
        ["Distance", f"{route.get('distance_km', route.get('distanceKm', '-'))} km"],
        ["Duration", f"{route.get('duration_hours', route.get('durationHours', '-'))} hours"],
        ["Budget", f"₹{total_inr:,.0f} / ${total_usd:,.2f}" if total_inr else f"₹{trip_data.get('budget', '-')}"],
        ["Toll roads", "Yes" if route.get("toll_roads") else "No"],
    ]
    story.append(_build_section_table("Trip Summary", trip_summary_rows, [180, 320]))
    story.append(Spacer(1, 16))

    story.append(Paragraph("Plan at a glance", styles["RoadMindSection"]))
    story.append(
        Paragraph(
            _text(
                trip_data.get(
                    "report_summary",
                    "This report summarizes the route, weather outlook, budget, and recommendations for your trip.",
                )
            ),
            styles["BodyText"],
        )
    )
    story.append(Spacer(1, 16))

    # Page 2
    story.append(Paragraph("Budget Breakdown", styles["RoadMindSection"]))
    story.append(
        Paragraph(
            "Estimated travel costs are split into major categories. Values are shown in both INR and USD for convenience.",
            styles["BodyText"],
        )
    )
    story.append(Spacer(1, 10))
    budget_rows = [
        ["Fuel", f"₹{fuel_inr:,.0f}", f"${fuel_inr / INR_PER_USD:,.2f}"],
        ["Tolls", f"₹{toll_inr:,.0f}", f"${toll_inr / INR_PER_USD:,.2f}"],
        ["Hotels", f"₹{hotel_inr:,.0f}", f"${hotel_inr / INR_PER_USD:,.2f}"],
        ["Food", f"₹{food_inr:,.0f}", f"${food_inr / INR_PER_USD:,.2f}"],
        ["Miscellaneous", f"₹{misc_inr:,.0f}", f"${misc_inr / INR_PER_USD:,.2f}"],
        ["Total", f"₹{total_inr:,.0f}", f"${total_usd:,.2f}"],
    ]
    budget_table = Table([["Category", "INR", "USD"], *budget_rows], colWidths=[190, 150, 150], repeatRows=1)
    budget_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor("#eef2ff")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(budget_table)

    story.append(Spacer(1, 16))

    # Page 3
    story.append(Paragraph("Recommendations", styles["RoadMindSection"]))
    story.append(
        Paragraph(
            "The final page groups the trip suggestions into hotels, restaurants, and attractions with short explanations from the trip planner.",
            styles["BodyText"],
        )
    )
    story.append(Spacer(1, 10))

    rec_sections = [
        ("Hotels", recommendations.get("hotels", [])),
        ("Restaurants", recommendations.get("restaurants", [])),
        ("Attractions", recommendations.get("attractions", [])),
    ]

    for section_name, entries in rec_sections:
        story.append(Paragraph(section_name, styles["Heading3"]))
        rec_rows = []
        for index, item in enumerate(entries[:3]):
            rec_rows.append(
                [
                    str(index + 1),
                    _text(item.get("name") or item.get("title")),
                    _text(item.get("description") or item.get("why_it_fits")),
                ]
            )
        if not rec_rows:
            rec_rows = [["-", "No recommendations available", ""]]

        rec_table = Table([["#", "Name", "Description"], *rec_rows], colWidths=[35, 140, 325], repeatRows=1)
        rec_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor("#f8fafc")]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(rec_table)
        story.append(Spacer(1, 12))

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return {"output_path": str(output), "status": "created"}
