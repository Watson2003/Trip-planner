from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any
import math
import urllib.parse

from reportlab.graphics.shapes import Circle, Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image as RLImage, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

import httpx

try:
    from PIL import Image as PILImage
    from PIL import ImageDraw
except Exception:  # pragma: no cover - optional dependency fallback
    PILImage = None
    ImageDraw = None

from utils.geo import haversine_distance_km
from agents.fallbacks import fallback_daily_weather


PRIMARY = colors.HexColor("#1D1D1F")
ACCENT = colors.HexColor("#0071E3")
SECONDARY = colors.HexColor("#6E6E73")
CARD_BG = colors.HexColor("#F7F8FA")
CARD_BORDER = colors.HexColor("#D7DCE3")
SUCCESS = colors.HexColor("#1F8B4C")
DANGER = colors.HexColor("#D92D20")
FOOTER_LINE = colors.HexColor("#E5E7EB")
INR_PER_USD = 83.0


def _normalize_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "".join(char if char.isalnum() else "-" for char in text).strip("-")


def _text(value: Any, default: str = "-") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return escape(text) if text else default


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _first_number(data: dict[str, Any], keys: list[str]) -> float:
    for key in keys:
        value = data.get(key)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            return float(value)
    return 0.0


def _positive_number(*values: Any) -> float:
    for value in values:
        if isinstance(value, (int, float)) and math.isfinite(float(value)) and float(value) > 0:
            return float(value)
        if isinstance(value, str):
            text = value.strip().replace(",", "")
            if text.startswith("₹"):
                text = text[1:].strip()
            try:
                parsed = float(text)
            except ValueError:
                continue
            if math.isfinite(parsed) and parsed > 0:
                return float(parsed)
    return 0.0


def _money(value: float) -> str:
    return f"₹{value:,.0f}"


def _money_usd(value: float) -> str:
    return f"${value / INR_PER_USD:,.2f}"


def _pretty_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%d %b, %Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%d %b %Y")
        except ValueError:
            continue
    return text


def _duration_text(hours: float) -> str:
    if not hours or hours <= 0:
        return "-"
    total_minutes = max(0, int(round(hours * 60)))
    whole_hours = total_minutes // 60
    minutes = total_minutes % 60
    if whole_hours == 0:
        return f"{minutes} min"
    if minutes == 0:
        return f"{whole_hours} hr"
    return f"{whole_hours} hr {minutes} min"


def _point_from_any(value: Any) -> tuple[float, float] | None:
    if isinstance(value, dict):
        lat = value.get("lat") if value.get("lat") is not None else value.get("latitude")
        lon = value.get("lng") if value.get("lng") is not None else value.get("lon") if value.get("lon") is not None else value.get("longitude")
    elif isinstance(value, (list, tuple)) and len(value) >= 2:
        lat, lon = value[0], value[1]
    else:
        return None

    if lat is None or lon is None:
        return None
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None


def _route_points_from_trip_data(trip_data: dict[str, Any]) -> tuple[list[tuple[float, float]], tuple[float, float] | None, tuple[float, float] | None]:
    route = _as_dict(trip_data.get("route"))
    raw_points = _as_list(trip_data.get("route_polyline") or route.get("polyline") or route.get("coordinates"))
    points = [point for point in (_point_from_any(item) for item in raw_points) if point is not None]
    origin_coords = _point_from_any(route.get("origin_coords") or trip_data.get("origin_coords"))
    destination_coords = _point_from_any(route.get("destination_coords") or trip_data.get("destination_coords"))

    if len(points) < 2:
        return [], origin_coords, destination_coords

    mean_first = sum(abs(point[0]) for point in points) / len(points)
    mean_second = sum(abs(point[1]) for point in points) / len(points)
    looks_like_lon_lat = mean_first > mean_second
    if looks_like_lon_lat:
        points = [(lon, lat) for lat, lon in points]

    if origin_coords and destination_coords:
        forward_score = haversine_distance_km(points[0][0], points[0][1], origin_coords[0], origin_coords[1]) + haversine_distance_km(
            points[-1][0], points[-1][1], destination_coords[0], destination_coords[1]
        )
        reversed_score = haversine_distance_km(points[0][0], points[0][1], destination_coords[0], destination_coords[1]) + haversine_distance_km(
            points[-1][0], points[-1][1], origin_coords[0], origin_coords[1]
        )
        if reversed_score + 0.5 < forward_score:
            points = list(reversed(points))

    return points, origin_coords, destination_coords


def _mercator_pixel(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    scale = 256 * (2**zoom)
    sin_lat = math.sin(math.radians(lat))
    x = (lon + 180.0) / 360.0 * scale
    y = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * scale
    return x, y


def _choose_zoom(points: list[tuple[float, float]], width: int, height: int, padding: int = 40) -> int:
    if len(points) < 2:
        return 10

    for zoom in range(15, 4, -1):
        pixels = [_mercator_pixel(lat, lon, zoom) for lat, lon in points]
        xs = [pixel[0] for pixel in pixels]
        ys = [pixel[1] for pixel in pixels]
        span_x = max(xs) - min(xs)
        span_y = max(ys) - min(ys)
        if span_x <= width - (padding * 2) and span_y <= height - (padding * 2):
            return zoom
    return 5


def _route_google_maps_link(origin: str, destination: str) -> str:
    return build_google_maps_directions_url(origin, destination)


def _build_static_route_map_image(
    points: list[tuple[float, float]],
    origin: str,
    destination: str,
    *,
    width: int = 980,
    height: int = 560,
) -> bytes | None:
    if PILImage is None or ImageDraw is None or len(points) < 2:
        return None

    zoom = _choose_zoom(points, width, height, padding=80)
    pixel_points = [_mercator_pixel(lat, lon, zoom) for lat, lon in points]
    xs = [point[0] for point in pixel_points]
    ys = [point[1] for point in pixel_points]
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    viewport_left = center_x - (width / 2)
    viewport_top = center_y - (height / 2)

    tile_left = int(math.floor(viewport_left / 256))
    tile_top = int(math.floor(viewport_top / 256))
    tile_right = int(math.floor((viewport_left + width - 1) / 256))
    tile_bottom = int(math.floor((viewport_top + height - 1) / 256))

    canvas = PILImage.new("RGB", (width, height), "#EAF2FA")
    try:
        with httpx.Client(timeout=12.0, headers={"User-Agent": "RoadMindAI/1.0"}) as client:
            for tile_x in range(tile_left, tile_right + 1):
                for tile_y in range(tile_top, tile_bottom + 1):
                    try:
                        response = client.get(f"https://tile.openstreetmap.org/{zoom}/{tile_x}/{tile_y}.png")
                        response.raise_for_status()
                        tile = PILImage.open(BytesIO(response.content)).convert("RGB")
                    except Exception:
                        tile = PILImage.new("RGB", (256, 256), "#EAF2FA")
                    paste_x = int((tile_x * 256) - viewport_left)
                    paste_y = int((tile_y * 256) - viewport_top)
                    canvas.paste(tile, (paste_x, paste_y))
    except Exception:
        return None

    draw = ImageDraw.Draw(canvas)
    route_pixels = [(x - viewport_left, y - viewport_top) for x, y in pixel_points]
    if len(route_pixels) < 2:
        return None

    draw.line(route_pixels, fill="#0071E3", width=7, joint="curve")
    origin_x, origin_y = route_pixels[0]
    destination_x, destination_y = route_pixels[-1]
    marker_radius = 10
    draw.ellipse(
        (origin_x - marker_radius, origin_y - marker_radius, origin_x + marker_radius, origin_y + marker_radius),
        fill="#1F8B4C",
        outline="#FFFFFF",
        width=3,
    )
    draw.ellipse(
        (destination_x - marker_radius, destination_y - marker_radius, destination_x + marker_radius, destination_y + marker_radius),
        fill="#D92D20",
        outline="#FFFFFF",
        width=3,
    )

    label_fill = "#FFFFFF"
    label_outline = "#D7DCE3"
    label_padding_x = 8
    label_padding_y = 5

    def _label(x: float, y: float, text: str, fill: str) -> None:
        text_bbox = draw.textbbox((0, 0), text)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        box_x1 = x + 14
        box_y1 = y - (text_height / 2) - label_padding_y
        box_x2 = box_x1 + text_width + (label_padding_x * 2)
        box_y2 = box_y1 + text_height + (label_padding_y * 2)
        draw.rounded_rectangle((box_x1, box_y1, box_x2, box_y2), radius=8, fill=label_fill, outline=label_outline, width=1)
        draw.text((box_x1 + label_padding_x, box_y1 + label_padding_y), text, fill=fill)

    _label(origin_x, origin_y, origin, "#1F8B4C")
    _label(destination_x, destination_y, destination, "#D92D20")

    output = BytesIO()
    canvas.save(output, format="PNG")
    output.seek(0)
    return output.read()


def _trip_day_count(trip_data: dict[str, Any], itinerary_days: list[dict[str, Any]]) -> int:
    total_days = _positive_number(trip_data.get("trip_days"))
    travel_dates = _as_dict(trip_data.get("travel_dates"))
    start = str(travel_dates.get("start") or trip_data.get("startDate") or "").strip()
    end = str(travel_dates.get("end") or trip_data.get("endDate") or "").strip()
    if start and end:
        try:
            start_date = datetime.fromisoformat(start).date()
            end_date = datetime.fromisoformat(end).date()
            span = (end_date - start_date).days + 1
            if span > 0:
                total_days = max(total_days, float(span))
        except ValueError:
            pass
    total_days = max(total_days, float(len(itinerary_days) or 0))
    return max(1, int(round(total_days or 1)))


def build_google_maps_directions_url(origin: str, destination: str) -> str:
    origin_encoded = urllib.parse.quote(origin)
    destination_encoded = urllib.parse.quote(destination)
    return (
        "https://www.google.com/maps/dir/"
        f"?api=1&origin={origin_encoded}&destination={destination_encoded}&travelmode=driving"
    )


def _header_footer(canvas, doc) -> None:
    page_num = canvas.getPageNumber()
    width, height = A4
    today = datetime.now().strftime("%d %b %Y")

    canvas.saveState()
    canvas.setStrokeColor(FOOTER_LINE)
    canvas.setLineWidth(0.8)
    canvas.line(doc.leftMargin, height - 34, width - doc.rightMargin, height - 34)
    canvas.line(doc.leftMargin, 34, width - doc.rightMargin, 34)

    canvas.setFillColor(PRIMARY)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(doc.leftMargin, height - 24, "RoadMind AI")
    canvas.setFont("Helvetica", 8.5)
    canvas.setFillColor(SECONDARY)
    canvas.drawRightString(width - doc.rightMargin, height - 24, f"Page {page_num}")
    canvas.drawString(doc.leftMargin, 20, f"RoadMind AI | Generated on {today}")
    canvas.drawRightString(width - doc.rightMargin, 20, "Travel Intelligence Platform")
    canvas.restoreState()


def _build_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="RM_Hero",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=28,
            leading=32,
            textColor=PRIMARY,
            alignment=TA_CENTER,
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="RM_Subtitle",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=11,
            leading=15,
            textColor=SECONDARY,
            alignment=TA_CENTER,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="RM_Section",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=20,
            textColor=PRIMARY,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="RM_SubSection",
            parent=styles["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=14,
            textColor=PRIMARY,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="RM_Body",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=PRIMARY,
        )
    )
    styles.add(
        ParagraphStyle(
            name="RM_Muted",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=SECONDARY,
        )
    )
    styles.add(
        ParagraphStyle(
            name="RM_Label",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=SECONDARY,
            alignment=TA_LEFT,
        )
    )
    styles.add(
        ParagraphStyle(
            name="RM_Link",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=13,
            textColor=ACCENT,
        )
    )
    return styles


def _card_table(items: list[tuple[str, str]], width: float) -> Table:
    styles = _build_styles()
    rows = []
    for label, value in items:
        rows.append(
            [
                Paragraph(escape(label), styles["RM_Label"]),
                Paragraph(escape(value), styles["RM_Body"]),
            ]
        )
    table = Table(rows, colWidths=[width * 0.38, width * 0.62])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.8, CARD_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, CARD_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _section_table(headers: list[str], rows: list[list[Any]], col_widths: list[float]) -> Table:
    formatted_rows: list[list[Any]] = []
    for row in rows:
        formatted_rows.append([Paragraph(str(cell), _build_styles()["RM_Body"]) if isinstance(cell, str) else cell for cell in row])
    table = Table([headers, *formatted_rows], colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.45, CARD_BORDER),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, CARD_BG]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _build_route_drawing(route_points: list[list[float]], origin: str, destination: str, width: float = 500, height: float = 240) -> Drawing:
    drawing = Drawing(width, height)
    drawing.add(Rect(0, 0, width, height, rx=18, ry=18, fillColor=colors.white, strokeColor=CARD_BORDER, strokeWidth=1))
    drawing.add(Rect(24, 26, width - 48, height - 52, rx=14, ry=14, fillColor=colors.HexColor("#F9FAFB"), strokeColor=colors.HexColor("#E5E7EB"), strokeWidth=1))
    drawing.add(String(34, height - 28, "Interactive Route Overview", fontName="Helvetica-Bold", fontSize=12, fillColor=PRIMARY))
    drawing.add(String(34, height - 44, f"{_text(origin)} -> {_text(destination)}", fontName="Helvetica", fontSize=9, fillColor=SECONDARY))

    if not route_points:
        drawing.add(String(width / 2 - 86, height / 2, "Route map unavailable", fontName="Helvetica", fontSize=10, fillColor=SECONDARY))
        return drawing

    latitudes = [point[0] for point in route_points if len(point) >= 2]
    longitudes = [point[1] for point in route_points if len(point) >= 2]
    min_lat = min(latitudes)
    max_lat = max(latitudes)
    min_lon = min(longitudes)
    max_lon = max(longitudes)

    inner_left = 42
    inner_bottom = 44
    inner_width = width - 84
    inner_height = height - 96
    lat_span = max(max_lat - min_lat, 1e-6)
    lon_span = max(max_lon - min_lon, 1e-6)

    def transform(lat: float, lon: float) -> tuple[float, float]:
        x = inner_left + ((lon - min_lon) / lon_span) * inner_width
        y = inner_bottom + ((lat - min_lat) / lat_span) * inner_height
        return x, y

    scaled_points = [transform(point[0], point[1]) for point in route_points if len(point) >= 2]
    for start, end in zip(scaled_points, scaled_points[1:]):
        drawing.add(Line(start[0], start[1], end[0], end[1], strokeColor=ACCENT, strokeWidth=2.8))

    origin_x, origin_y = scaled_points[0]
    destination_x, destination_y = scaled_points[-1]
    drawing.add(Circle(origin_x, origin_y, 5.5, fillColor=SUCCESS, strokeColor=colors.white, strokeWidth=1.2))
    drawing.add(Circle(destination_x, destination_y, 5.5, fillColor=DANGER, strokeColor=colors.white, strokeWidth=1.2))
    drawing.add(String(origin_x + 8, origin_y + 4, _text(origin), fontName="Helvetica-Bold", fontSize=8, fillColor=SUCCESS))
    drawing.add(String(destination_x + 8, destination_y - 10, _text(destination), fontName="Helvetica-Bold", fontSize=8, fillColor=DANGER))
    drawing.add(String(width - 120, 36, "Legend:", fontName="Helvetica-Bold", fontSize=8.5, fillColor=PRIMARY))
    drawing.add(Circle(width - 78, 37, 3.8, fillColor=SUCCESS, strokeColor=SUCCESS))
    drawing.add(String(width - 68, 34, "Origin", fontName="Helvetica", fontSize=8, fillColor=SECONDARY))
    drawing.add(Circle(width - 30, 37, 3.8, fillColor=DANGER, strokeColor=DANGER))
    drawing.add(String(width - 20, 34, "Dest", fontName="Helvetica", fontSize=8, fillColor=SECONDARY))
    return drawing


def _destination_weather(weather: list[dict[str, Any]], destination: str, start_date: Any) -> list[dict[str, Any]]:
    fallback_source = fallback_daily_weather(destination, days=5, start_date=None)
    fallback = [
        {
            "date": _pretty_date(item.get("date") or start_date),
            "day_name": item.get("day_name") or "Estimated",
            "location": destination,
            "temp_min_celsius": float(item.get("temp_min_celsius") or 0.0),
            "temp_max_celsius": float(item.get("temp_max_celsius") or 0.0),
            "temp_feels_like": float(item.get("temp_feels_like") or item.get("temp_max_celsius") or 0.0),
            "humidity_percent": int(item.get("humidity_percent") or 0),
            "condition": str(item.get("condition") or "Estimated weather"),
            "weather_icon": str(item.get("weather_icon") or ""),
            "wind_speed_kmh": float(item.get("wind_speed_kmh") or 0.0),
            "rain_chance_percent": int(item.get("rain_chance_percent") or 0),
            "alert": item.get("alert"),
        }
        for item in fallback_source[:5]
    ]
    if not weather:
        return fallback

    normalized_destination = _normalize_key(destination)
    destination_days = [
        day
        for day in weather
        if _normalize_key(day.get("location")) == normalized_destination
        or _normalize_key(day.get("destination")) == normalized_destination
        or _normalize_key(day.get("city")) == normalized_destination
    ]
    if not destination_days:
        return fallback

    if all(
        float(day.get("temp_max_celsius") or 0) == 0
        and float(day.get("temp_min_celsius") or 0) == 0
        and float(day.get("temp_feels_like") or 0) == 0
        for day in destination_days
    ):
        return fallback

    return destination_days


def _fallback_recommendation_entries(destination: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    label = destination.strip() or "Destination"
    return (
        [
            {
                "name": f"{label} Stay",
                "rating": 4.0,
                "estimated_cost_inr": 0,
                "price_range": "Estimated",
                "description": f"Recommended stay for {label}.",
            }
        ],
        [
            {
                "name": f"{label} Dining",
                "cuisine": "Local",
                "estimated_cost_inr": 0,
                "price_range": "Estimated",
                "description": f"Recommended dining option for {label}.",
            }
        ],
        [
            {
                "name": f"{label} Highlight",
                "type": "Attraction",
                "estimated_duration_minutes": 90,
                "description": f"Recommended sightseeing stop for {label}.",
            }
        ],
    )


def _slot_explicit_cost(slot: dict[str, Any]) -> float:
    activity = _as_dict(slot.get("activity"))
    return _positive_number(
        slot.get("estimated_cost_inr"),
        slot.get("estimated_cost"),
        slot.get("cost_inr"),
        slot.get("cost"),
        slot.get("activity_cost"),
        slot.get("estimatedCost"),
        activity.get("cost"),
        activity.get("estimated_cost"),
        activity.get("estimatedCost"),
    )


def _estimate_slot_cost(slot: dict[str, Any], trip_data: dict[str, Any], total_days: int) -> float:
    existing = _slot_explicit_cost(slot)
    if existing > 0:
        return existing

    budget = _as_dict(trip_data.get("budget"))
    total_budget = _positive_number(trip_data.get("total_inr"), budget.get("total"))
    day_budget = total_budget / max(total_days, 1) if total_budget > 0 else 0.0
    slot_type = str(slot.get("type") or slot.get("category") or slot.get("activity") or "").strip().lower()
    title = str(slot.get("title") or slot.get("activity") or slot.get("name") or "").strip().lower()

    if any(keyword in slot_type or keyword in title for keyword in ("breakfast",)):
        return round(max(220.0, day_budget * 0.08), 2)
    if any(keyword in slot_type or keyword in title for keyword in ("lunch",)):
        return round(max(350.0, day_budget * 0.12), 2)
    if any(keyword in slot_type or keyword in title for keyword in ("dinner",)):
        return round(max(450.0, day_budget * 0.14), 2)
    if any(keyword in slot_type or keyword in title for keyword in ("hotel", "stay", "check in")):
        return round(max(1200.0, day_budget * 0.35), 2)
    if any(keyword in slot_type or keyword in title for keyword in ("drive", "fuel", "travel")):
        route_share = _positive_number(trip_data.get("route_distance_km"), _as_dict(trip_data.get("route")).get("distance_km"))
        return round(max(250.0, day_budget * 0.10, route_share * 0.75), 2)
    if any(keyword in slot_type or keyword in title for keyword in ("attraction", "sightseeing", "visit")):
        return round(max(120.0, day_budget * 0.05), 2)
    return round(max(100.0, day_budget * 0.04), 2)


def _estimate_local_travel_cost(slot: dict[str, Any]) -> float:
    existing = _slot_explicit_cost(slot)
    if existing > 0:
        return existing

    distance = _positive_number(slot.get("distance_from_previous_km"))
    travel_minutes = _positive_number(slot.get("travel_time_minutes"), slot.get("estimated_duration_minutes"), slot.get("duration_minutes"))
    if distance > 0:
        return round(max(80.0, distance * 12.0), 2)
    if travel_minutes > 0:
        return round(max(80.0, travel_minutes * 2.0), 2)
    return 0.0


def _pdf_day_kind(day: dict[str, Any], day_number: int, total_days: int) -> str:
    if day_number <= 1:
        return "arrival"

    text_parts = [
        str(day.get("day_title") or ""),
        str(day.get("summary") or ""),
        str(day.get("location") or ""),
    ]
    for slot in _as_list(day.get("time_slots")):
        if isinstance(slot, dict):
            text_parts.extend(
                [
                    str(slot.get("type") or ""),
                    str(slot.get("category") or ""),
                    str(slot.get("title") or ""),
                    str(slot.get("activity") or ""),
                ]
            )
    lowered = " ".join(text_parts).casefold()
    return "return" if any(token in lowered for token in ("return", "back to ", "drive back", "head back")) and day_number == total_days else "sightseeing"


def _pdf_day_title(destination: str, day_kind: str, origin: str) -> str:
    if day_kind == "arrival":
        return f"Arrival and Sightseeing - {destination}"
    if day_kind == "return":
        return f"Return Day - {destination} to {origin}"
    return f"Destination Sightseeing - {destination}"


def _pdf_day_summary_rows(
    *,
    day: dict[str, Any],
    day_number: int,
    day_kind: str,
    destination: str,
    travel_dates: dict[str, Any],
    route_distance: float,
    route_duration: float,
) -> tuple[list[str], list[list[str]]]:
    date_value = _pretty_date(day.get("date") or travel_dates.get("start"))
    location_value = _text(day.get("location") or destination)
    if day_kind == "arrival":
        return (
            ["Date", "Location", "Route", "Distance", "Driving Hours"],
            [[date_value, location_value, f"{_text(day.get('day_title') or 'Arrival')}", f"{route_distance:,.2f} km" if route_distance else "-", _duration_text(route_duration)]],
        )
    if day_kind == "return":
        return (
            ["Date", "Location", "Route", "Distance", "Driving Hours"],
            [[date_value, location_value, f"Return to {_text(day.get('location') or destination)}", f"{route_distance:,.2f} km" if route_distance else "-", _duration_text(route_duration)]],
        )
    return (
        ["Date", "Location", "Day Type"],
        [[date_value, location_value, "Sightseeing Day"]],
    )


def _sanitize_pdf_day(
    *,
    day: dict[str, Any],
    day_number: int,
    day_kind: str,
    trip_data: dict[str, Any],
    origin: str,
    destination: str,
    total_days: int,
    route_distance: float,
    route_duration: float,
) -> dict[str, Any]:
    day_copy = dict(day)
    slots = _as_list(day_copy.get("time_slots"))
    fixed_slots: list[dict[str, Any]] = []

    def _normalize_slot_type(value: Any) -> str:
        return str(value or "").strip().lower()

    for raw_slot in slots:
        if not isinstance(raw_slot, dict):
            continue
        slot = dict(raw_slot)
        slot_type = _normalize_slot_type(slot.get("type") or slot.get("category"))
        title = str(slot.get("title") or slot.get("activity") or slot.get("name") or "").strip()
        title_lower = title.casefold()
        location = str(slot.get("location") or destination).strip() or destination

        if slot_type == "breakfast" or "breakfast" in title_lower:
            location = origin if day_number == 1 else destination
        elif slot_type in {"lunch", "dinner", "hotel", "attraction", "sightseeing"}:
            if day_number > 1:
                location = destination

        if slot_type == "drive" or "drive" in title_lower or "travel" in title_lower:
            if day_kind == "arrival":
                location = f"{origin} to {destination}"
                if not title:
                    title = "Drive"
            elif day_kind == "return":
                location = f"{destination} to {origin}"
                title = "Return travel"
            else:
                local_cost = _estimate_local_travel_cost(slot)
                if local_cost <= 0 and not _positive_number(slot.get("distance_from_previous_km"), slot.get("travel_time_minutes"), slot.get("estimated_duration_minutes"), slot.get("duration_minutes")):
                    continue
                title = "Local travel"
                location = destination
                slot["estimated_cost_inr"] = local_cost
                if _positive_number(slot.get("estimated_duration_minutes"), slot.get("duration_minutes")) <= 0:
                    slot["estimated_duration_minutes"] = 30

        slot["location"] = location
        slot["current_location_before"] = origin if day_kind == "arrival" and (slot_type == "breakfast" or "breakfast" in title_lower or slot_type == "drive" or "drive" in title_lower) else destination
        slot["current_location_after"] = destination if day_kind != "return" else origin
        slot["title"] = title or slot.get("title") or slot.get("activity") or "Activity"
        slot["activity"] = slot.get("activity") or slot["title"]

        slot_cost = _estimate_slot_cost(slot, trip_data, total_days)
        if day_kind != "arrival" and slot_type in {"drive", "travel"} and "local travel" in title.casefold():
            slot_cost = _estimate_local_travel_cost(slot)
        if _positive_number(slot.get("estimated_cost_inr"), slot.get("cost_inr"), slot.get("cost")) <= 0:
            slot["estimated_cost_inr"] = slot_cost
        if _positive_number(slot.get("estimated_duration_minutes"), slot.get("duration_minutes")) <= 0:
            if slot_type in {"hotel"}:
                slot["estimated_duration_minutes"] = 30
            elif slot_type in {"breakfast", "lunch", "dinner"}:
                slot["estimated_duration_minutes"] = 45
            elif slot_type in {"drive", "travel"}:
                slot["estimated_duration_minutes"] = 30 if day_kind != "arrival" else max(60, int(round(route_duration * 60 * 0.45)))
            else:
                slot["estimated_duration_minutes"] = 75
        fixed_slots.append(slot)

    if not fixed_slots:
        if day_kind == "arrival":
            fixed_slots = [
                {"time": "08:00", "type": "breakfast", "title": "Breakfast", "location": origin, "estimated_duration_minutes": 45, "estimated_cost_inr": _estimate_slot_cost({"type": "breakfast"}, trip_data, total_days), "reason": ""},
                {"time": "10:00", "type": "drive", "title": "Drive", "location": f"{origin} to {destination}", "estimated_duration_minutes": max(60, int(round(route_duration * 60 * 0.45))) if route_duration > 0 else 120, "estimated_cost_inr": 0, "reason": ""},
                {"time": "01:00", "type": "lunch", "title": "Lunch", "location": destination, "estimated_duration_minutes": 45, "estimated_cost_inr": _estimate_slot_cost({"type": "lunch"}, trip_data, total_days), "reason": ""},
                {"time": "03:00", "type": "attraction", "title": "Sightseeing", "location": destination, "estimated_duration_minutes": 90, "estimated_cost_inr": _estimate_slot_cost({"type": "attraction"}, trip_data, total_days), "reason": ""},
                {"time": "07:00", "type": "dinner", "title": "Dinner", "location": destination, "estimated_duration_minutes": 60, "estimated_cost_inr": _estimate_slot_cost({"type": "dinner"}, trip_data, total_days), "reason": ""},
                {"time": "09:00", "type": "hotel", "title": "Hotel", "location": destination, "estimated_duration_minutes": 30, "estimated_cost_inr": _estimate_slot_cost({"type": "hotel"}, trip_data, total_days), "reason": ""},
            ]
        else:
            fixed_slots = [
                {"time": "08:00", "type": "breakfast", "title": "Breakfast", "location": destination, "estimated_duration_minutes": 45, "estimated_cost_inr": _estimate_slot_cost({"type": "breakfast"}, trip_data, total_days), "reason": ""},
                {"time": "10:30", "type": "attraction", "title": "Sightseeing", "location": destination, "estimated_duration_minutes": 90, "estimated_cost_inr": _estimate_slot_cost({"type": "attraction"}, trip_data, total_days), "reason": ""},
                {"time": "01:00", "type": "lunch", "title": "Lunch", "location": destination, "estimated_duration_minutes": 45, "estimated_cost_inr": _estimate_slot_cost({"type": "lunch"}, trip_data, total_days), "reason": ""},
                {"time": "03:00", "type": "attraction", "title": "Sightseeing", "location": destination, "estimated_duration_minutes": 90, "estimated_cost_inr": _estimate_slot_cost({"type": "attraction"}, trip_data, total_days), "reason": ""},
                {"time": "07:00", "type": "dinner", "title": "Dinner", "location": destination, "estimated_duration_minutes": 60, "estimated_cost_inr": _estimate_slot_cost({"type": "dinner"}, trip_data, total_days), "reason": ""},
                {"time": "09:00", "type": "hotel", "title": "Hotel", "location": destination, "estimated_duration_minutes": 30, "estimated_cost_inr": _estimate_slot_cost({"type": "hotel"}, trip_data, total_days), "reason": ""},
            ]

    if day_kind == "arrival":
        day_distance = route_distance if route_distance > 0 else _positive_number(day_copy.get("distance_km"))
        day_hours = route_duration if route_duration > 0 else _positive_number(day_copy.get("driving_hours"))
    elif day_kind == "return":
        day_distance = route_distance if route_distance > 0 else 0.0
        day_hours = route_duration if route_duration > 0 else 0.0
    else:
        day_distance = _positive_number(day_copy.get("distance_km"))
        day_hours = _positive_number(day_copy.get("driving_hours"))

    day_total = _positive_number(day_copy.get("day_total_cost_inr"))
    if day_total <= 0:
        day_total = round(sum(_positive_number(slot.get("estimated_cost_inr"), slot.get("cost_inr"), slot.get("cost")) for slot in fixed_slots), 2)

    day_copy.update(
        {
            "day_number": day_number,
            "day_title": _pdf_day_title(destination, day_kind, origin),
            "distance_km": day_distance,
            "driving_hours": day_hours,
            "day_total_cost_inr": day_total,
            "time_slots": fixed_slots,
            "pdf_day_kind": day_kind,
        }
    )
    return day_copy


def _fallback_itinerary_days(trip_data: dict[str, Any]) -> list[dict[str, Any]]:
    trip_days = int(trip_data.get("trip_days") or trip_data.get("days") or 1)
    destination = str(trip_data.get("destination") or "-")
    origin = str(trip_data.get("origin") or "-")
    itinerary = _as_dict(trip_data.get("itinerary"))
    days = _as_list(itinerary.get("days"))
    route = _as_dict(trip_data.get("route"))
    route_distance = _positive_number(trip_data.get("distance_km"), trip_data.get("route_distance_km"), route.get("distance_km"))
    route_duration = _positive_number(trip_data.get("duration_hours"), trip_data.get("route_duration_hours"), route.get("duration_hours"))
    total_budget = _positive_number(trip_data.get("total_inr"), _as_dict(trip_data.get("budget")).get("total"))
    total_days = max(1, trip_days, len(days) if days else 0)
    if days:
        sanitized_days: list[dict[str, Any]] = []
        for index, day in enumerate(days):
            day_data = day if isinstance(day, dict) else {}
            day_number = int(_positive_number(day_data.get("day_number")) or index + 1)
            day_kind = _pdf_day_kind(day_data, day_number, total_days)
            sanitized_days.append(
                _sanitize_pdf_day(
                    day=day_data,
                    day_number=day_number,
                    day_kind=day_kind,
                    trip_data=trip_data,
                    origin=origin,
                    destination=destination,
                    total_days=total_days,
                    route_distance=route_distance,
                    route_duration=route_duration,
                )
            )
        return sanitized_days

    fallback_days: list[dict[str, Any]] = []
    for index in range(max(1, trip_days)):
        day_number = index + 1
        day_kind = "arrival" if day_number == 1 else "sightseeing"
        fallback_days.append(
            _sanitize_pdf_day(
                day={
                    "day_number": day_number,
                    "date": trip_data.get("startDate") or trip_data.get("travel_dates", {}).get("start") or "-",
                    "day_title": f"Day {day_number}",
                    "summary": f"Road trip planning for {origin} to {destination}.",
                    "location": destination,
                    "time_slots": [],
                    "day_total_cost_inr": 0,
                    "distance_km": route_distance if day_kind == "arrival" else 0,
                    "driving_hours": route_duration if day_kind == "arrival" else 0,
                    "highlights": [],
                },
                day_number=day_number,
                day_kind=day_kind,
                trip_data=trip_data,
                origin=origin,
                destination=destination,
                total_days=total_days,
                route_distance=route_distance,
                route_duration=route_duration,
            )
        )
    return fallback_days


def _recommendation_sections(trip_data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    recommendations = trip_data.get("recommendations") or {}
    if isinstance(recommendations, list):
        block = recommendations[0] if recommendations else {}
        recommendations = block if isinstance(block, dict) else {}
    recommendations = _as_dict(recommendations)
    return _as_list(recommendations.get("hotels")), _as_list(recommendations.get("restaurants")), _as_list(recommendations.get("attractions"))


def generate_pdf_report(trip_data: dict[str, Any], output_path: str) -> dict[str, Any]:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.75 * inch,
        title="RoadMind AI Travel Report",
        author="RoadMind AI",
    )

    styles = _build_styles()
    origin = str(trip_data.get("origin") or "-")
    destination = str(trip_data.get("destination") or "-")
    travel_dates = _as_dict(trip_data.get("travel_dates"))
    route = _as_dict(trip_data.get("route"))
    route_points = _as_list(trip_data.get("route_polyline") or route.get("polyline") or route.get("coordinates"))
    weather = _as_list(trip_data.get("weather"))
    budget = _as_dict(trip_data.get("budget"))
    itinerary = trip_data.get("itinerary")
    itinerary_days = _fallback_itinerary_days(trip_data)
    hotels, restaurants, attractions = _recommendation_sections(trip_data)
    if not hotels and not restaurants and not attractions:
        hotels, restaurants, attractions = _fallback_recommendation_entries(destination)
    route_points, origin_coords, destination_coords = _route_points_from_trip_data(trip_data)
    google_maps_link = _route_google_maps_link(origin, destination)
    route_map_bytes = _build_static_route_map_image(route_points, origin, destination)
    route_map_generated = route_map_bytes is not None
    print(f"pdf_route_points_count = {len(route_points)}")
    print(f"pdf_route_map_generated = {str(route_map_generated).lower()}")
    print(f"google_maps_link = {google_maps_link}")

    distance_km = _positive_number(
        trip_data.get("distance_km"),
        trip_data.get("route_distance_km"),
        route.get("distance_km"),
        route.get("distanceKm"),
    )
    if distance_km <= 0 and route_points:
        total = 0.0
        for previous, current in zip(route_points, route_points[1:]):
            if len(previous) < 2 or len(current) < 2:
                continue
            lat1, lon1 = float(previous[0]), float(previous[1])
            lat2, lon2 = float(current[0]), float(current[1])
            total += math.dist((lat1, lon1), (lat2, lon2))
        distance_km = round(total * 111, 2) if total > 0 else 0.0
    duration_hours = _positive_number(
        trip_data.get("duration_hours"),
        trip_data.get("route_duration_hours"),
        route.get("duration_hours"),
        route.get("durationHours"),
    )

    fuel_cost = _positive_number(
        trip_data.get("fuel_cost_inr"),
        budget.get("fuel_cost_inr"),
        budget.get("fuel"),
        budget.get("fuelInr"),
        _as_dict(trip_data.get("fuel_calculation")).get("total_fuel_cost_inr"),
    )
    hotel_cost = _positive_number(trip_data.get("hotel_cost_inr"), budget.get("hotels"), budget.get("hotel"), budget.get("lodging"))
    food_cost = _positive_number(trip_data.get("food_cost_inr"), budget.get("food"))
    toll_cost = _positive_number(trip_data.get("toll_cost_inr"), budget.get("tolls"))
    misc_cost = _positive_number(trip_data.get("misc_cost_inr"), budget.get("miscellaneous"))
    total_budget = _positive_number(trip_data.get("total_inr"), budget.get("total")) or (fuel_cost + hotel_cost + food_cost + toll_cost + misc_cost)
    cost_per_person = _positive_number(trip_data.get("cost_per_person_inr")) or round(total_budget / max(1, int(trip_data.get("number_of_people") or _as_dict(trip_data.get("vehicle")).get("number_of_people") or 1)), 2)
    total_days = _trip_day_count(trip_data, itinerary_days)
    weather_days = _destination_weather(weather, destination, travel_dates.get("start"))
    recommended_hotel = hotels[0] if hotels else {}
    top_attractions = attractions[:3]
    closing_message = "Generated by RoadMind AI"

    page_width = A4[0] - doc.leftMargin - doc.rightMargin

    story: list[Any] = []

    # Cover page
    story.extend(
        [
            Spacer(1, 28),
            Paragraph("RoadMind AI", styles["RM_Hero"]),
            Paragraph("Travel Intelligence", styles["RM_Subtitle"]),
            Spacer(1, 16),
            Paragraph(f"{_text(origin)} -> {_text(destination)}", styles["RM_Section"]),
            Paragraph("Trip report", styles["RM_Subtitle"]),
            Spacer(1, 20),
            _card_table(
                [
                    ("Travel Dates", f"{_pretty_date(travel_dates.get('start'))} to {_pretty_date(travel_dates.get('end'))}"),
                    ("Total Days", str(total_days)),
                    ("Estimated Budget", _money(total_budget)),
                    ("Distance", f"{distance_km:,.2f} km" if distance_km else "-"),
                    ("Duration", _duration_text(duration_hours)),
                ],
                page_width,
            ),
            Spacer(1, 18),
            Paragraph(
                _text(trip_data.get("report_summary") or f"Route intelligence, weather, budget, recommendations, and itinerary for {_text(origin)} to {_text(destination)}."),
                styles["RM_Body"],
            ),
            Spacer(1, 8),
            Paragraph("RoadMind AI | Travel Intelligence Platform", styles["RM_Muted"]),
            PageBreak(),
        ]
    )

    # Route page
    route_link_paragraph = Paragraph(f'<link href="{escape(google_maps_link)}">Open route in Google Maps</link>', styles["RM_Link"])
    story.extend(
        [
            Paragraph("Trip Route Map", styles["RM_Section"]),
            Paragraph("Interactive Route Overview", styles["RM_Subtitle"]),
            Spacer(1, 10),
        ]
    )
    if route_map_bytes:
        map_image = RLImage(BytesIO(route_map_bytes), width=page_width, height=page_width * 0.55)
        story.extend(
            [
                map_image,
                Spacer(1, 10),
            ]
        )
    else:
        story.extend(
            [
                _card_table(
                    [
                        ("Route Summary", f"{_text(origin)} -> {_text(destination)}"),
                        ("Distance", f"{distance_km:,.2f} km" if distance_km else "-"),
                        ("Duration", _duration_text(duration_hours)),
                        ("Map", "Route image unavailable, but Google Maps link is included below."),
                    ],
                    page_width,
                ),
                Spacer(1, 10),
            ]
        )
    story.extend(
        [
            _card_table(
                [
                    ("Route", f"{_text(origin)} -> {_text(destination)}"),
                    ("Distance", f"{distance_km:,.2f} km" if distance_km else "-"),
                    ("Duration", _duration_text(duration_hours)),
                    ("Route Direction", f"{_text(origin)} -> {_text(destination)}"),
                ],
                page_width,
            ),
            Spacer(1, 8),
            route_link_paragraph,
            PageBreak(),
        ]
    )

    # Weather page
    story.extend(
        [
            Paragraph("Destination Weather", styles["RM_Section"]),
            Paragraph(f"Location: {_text(destination)}", styles["RM_Subtitle"]),
            Spacer(1, 10),
        ]
    )
    weather_rows: list[list[Any]] = []
    for day in weather_days[:5]:
        icon = str(day.get("weather_icon") or "").strip()
        weather_rows.append(
            [
                _text(day.get("date") or day.get("day_name")),
                _text(day.get("location") or destination),
                icon[:2] if icon else "N/A",
                f"{float(day.get('temp_max_celsius') or 0):.1f} C",
                f"{float(day.get('temp_feels_like') or 0):.1f} C",
                f"{int(day.get('humidity_percent') or 0)}%",
                f"{float(day.get('wind_speed_kmh') or 0):.1f} km/h",
                f"{int(day.get('rain_chance_percent') or 0)}%",
                _text(day.get("condition") or "Estimated weather"),
            ]
        )
    story.append(
        _section_table(
            ["Date", "Location", "Icon", "Temp", "Feels Like", "Humidity", "Wind", "Rain", "Description"],
            weather_rows or [[_pretty_date(travel_dates.get("start")), destination, "N/A", "-", "-", "-", "-", "-", "Estimated weather"]],
            [62, 74, 40, 50, 58, 50, 56, 45, 110],
        )
    )
    story.append(PageBreak())

    # Day-by-day pages
    for index, day in enumerate(itinerary_days):
        if index > 0:
            story.append(PageBreak())

        day_number = int(day.get("day_number") or index + 1)
        day_kind = str(day.get("pdf_day_kind") or _pdf_day_kind(day, day_number, total_days))
        day_view = _sanitize_pdf_day(
            day=day if isinstance(day, dict) else {},
            day_number=day_number,
            day_kind=day_kind,
            trip_data=trip_data,
            origin=origin,
            destination=destination,
            total_days=total_days,
            route_distance=distance_km,
            route_duration=duration_hours,
        )
        day_title = _text(day_view.get("day_title") or f"Day {day_number}")
        summary_headers, summary_rows = _pdf_day_summary_rows(
            day=day_view,
            day_number=day_number,
            day_kind=day_kind,
            destination=destination,
            travel_dates=travel_dates,
            route_distance=distance_km,
            route_duration=duration_hours,
        )
        story.extend(
            [
                Paragraph(f"Day {day_number}", styles["RM_Section"]),
                Paragraph(day_title, styles["RM_Subtitle"]),
                Spacer(1, 8),
                _section_table(summary_headers, summary_rows, [120, 120, 140, 90, 90][: len(summary_headers)]),
                Spacer(1, 10),
            ]
        )

        slots = _as_list(day_view.get("time_slots"))
        slot_rows: list[list[Any]] = []
        for slot in slots:
            raw_cost = _slot_explicit_cost(slot)
            if raw_cost <= 0:
                slot_type = str(slot.get("type") or slot.get("category") or "").strip().lower()
                title = str(slot.get("title") or slot.get("activity") or slot.get("name") or "").strip().lower()
                if "drive" in slot_type or "travel" in slot_type or "drive" in title or "travel" in title:
                    raw_cost = _estimate_local_travel_cost(slot)
                else:
                    raw_cost = _estimate_slot_cost(slot, trip_data, total_days)
            slot_rows.append(
                [
                    _text(slot.get("time")),
                    _text(slot.get("type") or slot.get("category") or "activity"),
                    _text(slot.get("title") or slot.get("activity") or slot.get("name")),
                    _text(slot.get("location") or destination),
                    _text(f"{slot.get('duration_minutes') or slot.get('estimated_duration_minutes') or 0} min"),
                    _money(raw_cost),
                ]
            )
        if not slot_rows:
            slot_rows = [["-", "Activity", "Itinerary unavailable", destination, "-", "₹0"]]
        story.append(
            _section_table(
                ["Time", "Type", "Name", "Location", "Duration", "Estimated Cost"],
                slot_rows,
                [58, 70, 150, 115, 65, 72],
            )
        )
        highlights = [str(item).strip() for item in _as_list(day.get("highlights")) if str(item).strip()]
        if highlights:
            story.append(Spacer(1, 8))
            story.append(Paragraph(f"Highlights: {', '.join(highlights)}", styles["RM_Muted"]))

    story.append(PageBreak())

    # Recommendations page
    story.extend(
        [
            Paragraph("Recommendations", styles["RM_Section"]),
            Paragraph("Hotels, restaurants, and attractions grouped separately.", styles["RM_Subtitle"]),
            Spacer(1, 8),
        ]
    )
    sections = [
        ("Hotels", hotels, ["Name", "Rating", "Price"]),
        ("Restaurants", restaurants, ["Name", "Cuisine", "Estimated Price"]),
        ("Attractions", attractions, ["Name", "Category", "Estimated Duration"]),
    ]
    for section_title, entries, headers in sections:
        story.append(Paragraph(section_title, styles["RM_SubSection"]))
        rows: list[list[Any]] = []
        for entry in entries[:6]:
            name = _text(entry.get("name") or entry.get("title"))
            rating = f"{float(entry.get('rating') or 0):.1f}"
            if section_title == "Hotels":
                price = _money(float(entry.get("estimated_cost_inr") or 0)) if entry.get("estimated_cost_inr") is not None else _text(entry.get("price_range") or entry.get("price_level"))
                rows.append([name, rating, price])
            elif section_title == "Restaurants":
                cuisine = _text(entry.get("cuisine") or entry.get("category") or "Local")
                price = _money(float(entry.get("estimated_cost_inr") or 0)) if entry.get("estimated_cost_inr") is not None else _text(entry.get("price_range") or entry.get("price_level"))
                rows.append([name, cuisine, price])
            else:
                category = _text(entry.get("type") or entry.get("category") or "Sightseeing")
                duration = _text(entry.get("estimated_duration_minutes") or entry.get("duration_minutes") or entry.get("entry_fee_inr") or "90 min")
                rows.append([name, category, duration])
        if not rows:
            rows = [["No recommendations available", "-", "-"]]
        story.append(_section_table(headers, rows, [180, 150, 190]))
        story.append(Spacer(1, 10))
    # Summary page
    story.extend(
        [
            Paragraph("Trip Summary", styles["RM_Section"]),
            Paragraph("A final snapshot of the RoadMind AI plan.", styles["RM_Subtitle"]),
            Spacer(1, 8),
            _card_table(
                [
                    ("Origin", origin),
                    ("Destination", destination),
                    ("Distance", f"{distance_km:,.2f} km" if distance_km else "-"),
                    ("Duration", _duration_text(duration_hours)),
                    ("Days", str(total_days)),
                    ("Budget", _money(total_budget)),
                ],
                page_width,
            ),
            Spacer(1, 12),
            Paragraph("Top Attractions", styles["RM_SubSection"]),
        ]
    )
    top_attraction_rows = [[_text(item.get("name")), _text(item.get("type") or item.get("category") or "Attraction")] for item in top_attractions]
    if not top_attraction_rows:
        top_attraction_rows = [["No attractions available", "-"]]
    story.append(_section_table(["Name", "Category"], top_attraction_rows, [255, 235]))
    story.extend(
        [
            Spacer(1, 10),
            Paragraph("Weather Summary", styles["RM_SubSection"]),
        ]
    )
    weather_summary_rows = [
        [
            _text(day.get("date") or day.get("day_name")),
            _text(day.get("condition") or "Estimated weather"),
            f"{float(day.get('temp_max_celsius') or 0):.1f} C",
        ]
        for day in weather_days[:3]
    ]
    if not weather_summary_rows:
        weather_summary_rows = [["-", "Estimated weather", "-"]]
    story.append(_section_table(["Date", "Condition", "High"], weather_summary_rows, [120, 230, 140]))
    story.extend(
        [
            Spacer(1, 10),
            Paragraph("Recommended Hotel", styles["RM_SubSection"]),
            Paragraph(
                _text(
                    recommended_hotel.get("name")
                    or recommended_hotel.get("title")
                    or "No recommendation available"
                ),
                styles["RM_Body"],
            ),
            Spacer(1, 8),
            Paragraph(f"{closing_message} | {_text(origin)} to {_text(destination)}", styles["RM_Muted"]),
            Spacer(1, 8),
            Paragraph(f'<link href="{escape(google_maps_link)}">Open route in Google Maps</link>', styles["RM_Link"]),
        ]
    )

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return {"output_path": str(output), "status": "created"}
