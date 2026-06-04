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
    PageBreak,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    SimpleDocTemplate,
    Flowable,
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


class RouteMapPlaceholder(Flowable):
    """A simple vector illustration that stands in for the route map on page 2."""

    def __init__(self, width: float = 6.6 * inch, height: float = 3.3 * inch) -> None:
        super().__init__()
        self.width = width
        self.height = height

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        return min(self.width, availWidth), min(self.height, availHeight)

    def draw(self) -> None:
        canvas = self.canv
        width = self.width
        height = self.height

        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#0f172a"))
        canvas.setFillColor(colors.HexColor("#eff6ff"))
        canvas.roundRect(0, 0, width, height, 18, stroke=1, fill=1)

        canvas.setStrokeColor(colors.HexColor("#94a3b8"))
        canvas.setLineWidth(2.5)
        canvas.line(50, height - 55, width - 50, 60)
        canvas.setStrokeColor(colors.HexColor("#f59e0b"))
        canvas.setLineWidth(5)
        canvas.line(80, 70, width * 0.46, height * 0.58)
        canvas.line(width * 0.46, height * 0.58, width * 0.68, height * 0.42)
        canvas.line(width * 0.68, height * 0.42, width - 85, height - 70)

        for x, y, label, color in [
            (65, 70, "Origin", colors.HexColor("#2563eb")),
            (width * 0.46, height * 0.58, "Waypoint", colors.HexColor("#7c3aed")),
            (width * 0.68, height * 0.42, "Waypoint", colors.HexColor("#7c3aed")),
            (width - 80, height - 70, "Destination", colors.HexColor("#dc2626")),
        ]:
            canvas.setFillColor(color)
            canvas.circle(x, y, 9, stroke=0, fill=1)
            canvas.setFillColor(colors.white)
            canvas.circle(x, y, 3, stroke=0, fill=1)
            canvas.setFillColor(colors.HexColor("#0f172a"))
            canvas.setFont("Helvetica-Bold", 9)
            canvas.drawString(x + 14, y - 3, label)

        canvas.setFillColor(colors.HexColor("#334155"))
        canvas.setFont("Helvetica-Bold", 14)
        canvas.drawCentredString(width / 2, height - 28, "Route map preview")
        canvas.setFont("Helvetica", 10)
        canvas.drawCentredString(width / 2, 18, "Placeholder map graphic for the generated PDF report")
        canvas.restoreState()


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
    weather = trip_data.get("weather") or []
    recommendations = trip_data.get("recommendations") or {}
    budget = trip_data.get("budget") or {}
    waypoints = trip_data.get("waypoints") or []

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
    story.append(Spacer(1, 10))
    story.append(
        Table(
            [[
                Paragraph("<b>Waypoints</b>", styles["BodyText"]),
                Paragraph(_text(", ".join(waypoints) if waypoints else "No waypoints provided"), styles["BodyText"]),
            ]],
            colWidths=[130, 370],
        )
    )

    story.append(PageBreak())

    # Page 2
    story.append(Paragraph("Route Overview", styles["RoadMindSection"]))
    story.append(
        Paragraph(
            "The placeholder map below represents the planned road route and the main stopping points on the journey.",
            styles["BodyText"],
        )
    )
    story.append(Spacer(1, 12))
    story.append(RouteMapPlaceholder())
    story.append(Spacer(1, 16))
    story.append(Paragraph("Waypoints", styles["RoadMindSection"]))
    waypoint_rows = [[str(index + 1), _text(waypoint)] for index, waypoint in enumerate(waypoints)] or [["-", "No waypoints provided"]]
    story.append(_build_section_table("Stops", waypoint_rows, [60, 440]))

    story.append(PageBreak())

    # Page 3
    story.append(Paragraph("Weather Forecast", styles["RoadMindSection"]))
    story.append(
        Paragraph(
            "The table below summarizes the provided weather data for the trip origin, destination, and any intermediate stops.",
            styles["BodyText"],
        )
    )
    story.append(Spacer(1, 10))
    weather_rows = []
    for item in weather:
        weather_rows.append(
            [
                _text(item.get("location") or item.get("city")),
                _text(item.get("day") or item.get("date")),
                _text(item.get("temperatureC") or item.get("temp_celsius") or item.get("highC")),
                _text(item.get("condition")),
                _text(item.get("severeAlert") or item.get("alert") or "-"),
            ]
        )
    if not weather_rows:
        weather_rows = [["-", "-", "-", "-", "No weather data provided"]]
    weather_table = Table(
        [["Location", "Day", "Temp (°C)", "Condition", "Alert"], *weather_rows],
        colWidths=[110, 90, 70, 140, 130],
        repeatRows=1,
    )
    weather_table.setStyle(
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
    story.append(weather_table)

    story.append(PageBreak())

    # Page 4
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

    story.append(PageBreak())

    # Page 5
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
