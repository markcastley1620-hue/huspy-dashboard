"""
Premium PDF brochure generator for property listings.
World-class real estate brochure with cohesive design.
"""

import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle,
    PageBreak, KeepTogether, HRFlowable,
)
from reportlab.graphics.shapes import Drawing, Rect, Line
from reportlab.graphics import renderPDF
from PIL import Image as PILImage

# ── Design tokens ──
CHARCOAL = colors.HexColor("#1C1C1E")
SLATE = colors.HexColor("#3A3A3C")
WARM_GREY = colors.HexColor("#8E8E93")
LIGHT_GREY = colors.HexColor("#F2F2F7")
DIVIDER_GREY = colors.HexColor("#D1D1D6")
GOLD = colors.HexColor("#B08D57")
WHITE = colors.white
PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


def _styles():
    """Build all paragraph styles."""
    s = {}

    s["hero_title"] = ParagraphStyle(
        "hero_title", fontSize=22, leading=28, fontName="Helvetica-Bold",
        textColor=CHARCOAL, spaceAfter=3 * mm, alignment=TA_LEFT,
    )
    s["hero_subtitle"] = ParagraphStyle(
        "hero_subtitle", fontSize=11, leading=16, fontName="Helvetica",
        textColor=WARM_GREY, spaceAfter=1 * mm,
    )
    s["price"] = ParagraphStyle(
        "price", fontSize=26, leading=32, fontName="Helvetica-Bold",
        textColor=CHARCOAL, spaceAfter=2 * mm,
    )
    s["location"] = ParagraphStyle(
        "location", fontSize=12, leading=17, fontName="Helvetica",
        textColor=SLATE, spaceAfter=6 * mm,
    )
    s["stat_value"] = ParagraphStyle(
        "stat_value", fontSize=20, leading=24, fontName="Helvetica-Bold",
        textColor=CHARCOAL, alignment=TA_CENTER,
    )
    s["stat_label"] = ParagraphStyle(
        "stat_label", fontSize=8, leading=12, fontName="Helvetica",
        textColor=WARM_GREY, alignment=TA_CENTER, spaceAfter=0,
    )
    s["section"] = ParagraphStyle(
        "section", fontSize=9, leading=12, fontName="Helvetica-Bold",
        textColor=GOLD, spaceBefore=6 * mm, spaceAfter=3 * mm,
        tracking=2,
    )
    s["detail_label"] = ParagraphStyle(
        "detail_label", fontSize=9, leading=13, fontName="Helvetica",
        textColor=WARM_GREY,
    )
    s["detail_value"] = ParagraphStyle(
        "detail_value", fontSize=11, leading=15, fontName="Helvetica-Bold",
        textColor=CHARCOAL,
    )
    s["agent_name"] = ParagraphStyle(
        "agent_name", fontSize=13, leading=17, fontName="Helvetica-Bold",
        textColor=CHARCOAL,
    )
    s["agent_detail"] = ParagraphStyle(
        "agent_detail", fontSize=9, leading=14, fontName="Helvetica",
        textColor=SLATE,
    )
    s["footer"] = ParagraphStyle(
        "footer", fontSize=7, leading=10, fontName="Helvetica",
        textColor=WARM_GREY, alignment=TA_CENTER,
    )
    s["gallery_header"] = ParagraphStyle(
        "gallery_header", fontSize=9, leading=12, fontName="Helvetica-Bold",
        textColor=GOLD, spaceAfter=4 * mm, tracking=2,
    )
    return s


def _img_dims(path, max_w, max_h):
    """Image dimensions maintaining aspect ratio."""
    img = PILImage.open(path)
    w, h = img.size
    r = min(max_w / w, max_h / h)
    return w * r, h * r


def _gold_rule(width):
    """Thin gold horizontal rule."""
    return HRFlowable(
        width="100%", thickness=0.75, color=GOLD,
        spaceAfter=4 * mm, spaceBefore=2 * mm,
    )


def _stat_cell(value, label, styles):
    """Single stat block for the key-figures row."""
    return [
        Paragraph(str(value), styles["stat_value"]),
        Paragraph(label.upper(), styles["stat_label"]),
    ]


def generate_brochure(property_data: dict, image_paths: list, output_path: str,
                      branding: dict | None = None):
    """Generate a premium property brochure PDF."""
    branding = branding or {}
    S = _styles()

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
    )

    story = []

    # ════════════════════════════════════════════
    # PAGE 1 — Hero + Key Info + Agent Card
    # ════════════════════════════════════════════

    # ── Hero image ──
    if image_paths:
        try:
            iw, ih = _img_dims(image_paths[0], CONTENT_W, 115 * mm)
            hero = Image(image_paths[0], width=iw, height=ih)
            hero.hAlign = "CENTER"
            story.append(hero)
        except Exception:
            pass
    story.append(Spacer(1, 6 * mm))

    # ── Price ──
    price = property_data.get("price") or "Price on Request"
    story.append(Paragraph(price, S["price"]))

    # ── Title ──
    title = property_data.get("title") or "Property Listing"
    story.append(Paragraph(title, S["hero_title"]))

    # ── Location ──
    location = property_data.get("location") or ""
    if location:
        story.append(Paragraph(location, S["location"]))

    # ── Gold rule ──
    story.append(_gold_rule(CONTENT_W))

    # ── Key stats row (beds / baths / size) ──
    stat_items = []
    if property_data.get("bedrooms"):
        stat_items.append(("bedrooms", property_data["bedrooms"], "Bedrooms"))
    if property_data.get("bathrooms"):
        stat_items.append(("baths", property_data["bathrooms"], "Bathrooms"))
    if property_data.get("size"):
        stat_items.append(("size", property_data["size"], "Total Area"))

    if stat_items:
        cells = []
        for _, val, label in stat_items:
            cells.append(_stat_cell(val, label, S))

        n = len(cells)
        col_w = CONTENT_W / n if n else CONTENT_W
        stat_table = Table([cells], colWidths=[col_w] * n)

        # Vertical dividers between stat cells
        style_cmds = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
        ]
        for i in range(1, n):
            style_cmds.append(("LINEAFTER", (i - 1, 0), (i - 1, 0), 0.5, DIVIDER_GREY))

        stat_table.setStyle(TableStyle(style_cmds))
        story.append(stat_table)
        story.append(Spacer(1, 2 * mm))
        story.append(_gold_rule(CONTENT_W))

    # ── Property details grid ──
    detail_items = [
        ("Type", property_data.get("type")),
        ("Purpose", property_data.get("purpose")),
        ("Furnishing", property_data.get("furnishing")),
        ("Completion", property_data.get("completion")),
        ("Reference", property_data.get("reference")),
        ("Permit", property_data.get("permit_number")),
    ]
    active = [(k, v) for k, v in detail_items if v]

    if active:
        story.append(Paragraph("PROPERTY DETAILS", S["section"]))

        rows = []
        for i in range(0, len(active), 3):
            row = []
            for j in range(3):
                if i + j < len(active):
                    label, value = active[i + j]
                    row.append([
                        Paragraph(label.upper(), S["detail_label"]),
                        Spacer(1, 1 * mm),
                        Paragraph(str(value), S["detail_value"]),
                    ])
                else:
                    row.append([Paragraph("", S["detail_label"])])
            rows.append(row)

        col_w = CONTENT_W / 3
        detail_table = Table(rows, colWidths=[col_w] * 3)
        detail_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
        ]))
        story.append(detail_table)

    # ── Agent card ──
    if branding and any(branding.get(k) for k in ("agent_name", "phone", "email")):
        story.append(Spacer(1, 4 * mm))
        story.append(_gold_rule(CONTENT_W))
        story.append(Spacer(1, 2 * mm))

        # Photo
        photo_cell = Paragraph("", S["footer"])
        photo_col_w = 0
        if branding.get("photo_path") and os.path.exists(branding["photo_path"]):
            try:
                pw, ph = _img_dims(branding["photo_path"], 20 * mm, 20 * mm)
                photo_cell = Image(branding["photo_path"], width=pw, height=ph)
                photo_col_w = 26 * mm
            except Exception:
                pass

        # Details
        lines = []
        if branding.get("agent_name"):
            lines.append(Paragraph(branding["agent_name"], S["agent_name"]))
        contact = []
        if branding.get("phone"):
            contact.append(branding["phone"])
        if branding.get("email"):
            contact.append(branding["email"])
        if branding.get("company"):
            contact.append(branding["company"])
        if contact:
            lines.append(Spacer(1, 1 * mm))
            lines.append(Paragraph("  ·  ".join(contact), S["agent_detail"]))

        if photo_col_w:
            card = Table(
                [[photo_cell, lines]],
                colWidths=[photo_col_w, CONTENT_W - photo_col_w],
            )
            card.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (1, 0), (1, 0), 4 * mm),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("RIGHTPADDING", (-1, -1), (-1, -1), 0),
            ]))
            story.append(card)
        else:
            story.extend(lines)

    # ════════════════════════════════════════════
    # GALLERY — flows directly after page 1 content
    # ════════════════════════════════════════════
    if len(image_paths) > 1:
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph("GALLERY", S["gallery_header"]))
        story.append(_gold_rule(CONTENT_W))
        story.append(Spacer(1, 2 * mm))

        remaining = image_paths[1:]  # image 1 is hero, maintain order

        # 2-up grid
        gap = 3 * mm
        img_w = (CONTENT_W - gap) / 2
        img_h = 75 * mm

        for i in range(0, len(remaining), 2):
            pair = remaining[i:i + 2]
            cells = []
            for p in pair:
                try:
                    iw, ih = _img_dims(p, img_w, img_h)
                    cells.append(Image(p, width=iw, height=ih))
                except Exception:
                    cells.append(Paragraph("", S["footer"]))

            if len(cells) == 1:
                cells[0].hAlign = "CENTER"
                story.append(cells[0])
            else:
                tbl = Table([cells], colWidths=[CONTENT_W / 2, CONTENT_W / 2])
                tbl.setStyle(TableStyle([
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ]))
                story.append(tbl)
            story.append(Spacer(1, gap))

        # Compact agent contact at end of gallery
        if branding and any(branding.get(k) for k in ("agent_name", "phone", "email")):
            story.append(Spacer(1, 3 * mm))
            story.append(_gold_rule(CONTENT_W))
            story.append(Spacer(1, 1 * mm))
            contact_line = []
            if branding.get("agent_name"):
                contact_line.append(f"<b>{branding['agent_name']}</b>")
            if branding.get("phone"):
                contact_line.append(branding["phone"])
            if branding.get("email"):
                contact_line.append(branding["email"])
            story.append(Paragraph("  ·  ".join(contact_line), ParagraphStyle(
                "mini_agent", fontSize=9, leading=13, fontName="Helvetica",
                textColor=SLATE, alignment=TA_CENTER,
            )))

    # Build
    doc.build(story)
    return output_path
