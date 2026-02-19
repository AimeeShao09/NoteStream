from __future__ import annotations

import html
import io
import re
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from notestream.mindmap_renderer import render_mind_map_drawing

def _build_styles() -> dict[str, ParagraphStyle]:
    styles = getSampleStyleSheet()
    return {
        "title": styles["Title"],
        "h1": styles["Heading1"],
        "h2": styles["Heading2"],
        "h3": styles["Heading3"],
        "body": styles["BodyText"],
        "bullet": ParagraphStyle(
            "Bullet",
            parent=styles["BodyText"],
            leftIndent=14,
            bulletIndent=4,
            spaceAfter=4,
        ),
        "meta": ParagraphStyle(
            "Meta",
            parent=styles["BodyText"],
            fontSize=9,
            leading=12,
            textColor="#5A5A5A",
        ),
        "code": ParagraphStyle(
            "Code",
            parent=styles["Code"],
            fontName="Courier",
            fontSize=9,
            leading=11,
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=styles["BodyText"],
            fontSize=10,
            leading=13,
        ),
        "table_cell": ParagraphStyle(
            "TableCell",
            parent=styles["BodyText"],
            fontSize=10,
            leading=14,
        ),
        "summary": ParagraphStyle(
            "Summary",
            parent=styles["BodyText"],
            fontSize=10,
            leading=14,
        ),
    }


def _is_table_separator(line: str) -> bool:
    return bool(
        re.match(r"^\s*\|?(\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$", line)
    )


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def _safe_inline(text: str, keep_breaks: bool = False) -> str:
    normalized = re.sub(r"<br\s*/?>", "\n" if keep_breaks else " | ", text, flags=re.IGNORECASE)
    # Remove markdown fence markers such as ```text / ``` that can leak into output.
    normalized = re.sub(r"(?im)^\s*```[\w-]*\s*$", "", normalized)
    normalized = normalized.replace("```", "")
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    escaped = html.escape(normalized, quote=False)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"\*(.+?)\*", r"<i>\1</i>", escaped)
    escaped = escaped.replace("`", "")
    if keep_breaks:
        escaped = escaped.replace("\n", "<br/>")
    return escaped


def _build_table_flowable(
    headers: list[str],
    rows: list[list[str]],
    styles: dict[str, ParagraphStyle],
    content_width: float,
) -> Table:
    header_cells = [Paragraph(_safe_inline(cell), styles["table_header"]) for cell in headers]
    body_cells = [
        [Paragraph(_safe_inline(cell, keep_breaks=True), styles["table_cell"]) for cell in row]
        for row in rows
    ]
    data = [header_cells] + body_cells
    col_count = len(headers)

    if col_count == 2:
        col_widths = [content_width * 0.28, content_width * 0.72]
    else:
        col_widths = [content_width / max(col_count, 1)] * col_count

    table = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf1ff")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _markdown_to_story(markdown: str, styles: dict[str, ParagraphStyle], content_width: float) -> list:
    story: list = []
    in_code = False
    code_lines: list[str] = []
    indent_style_cache: dict[tuple[str, int], ParagraphStyle] = {}
    lines = markdown.splitlines()
    i = 0

    def _with_indent(style_name: str, indent: int) -> ParagraphStyle:
        key = (style_name, indent)
        if key not in indent_style_cache:
            indent_style_cache[key] = ParagraphStyle(
                f"{style_name}_indent_{indent}",
                parent=styles[style_name],
                leftIndent=indent,
            )
        return indent_style_cache[key]

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                story.append(Preformatted("\n".join(code_lines), styles["code"]))
                story.append(Spacer(1, 8))
                in_code = False
                code_lines = []
            else:
                in_code = True
            i += 1
            continue

        if in_code:
            code_lines.append(line)
            i += 1
            continue

        if re.match(r"^\s*[-*_]{3,}\s*$", line):
            story.append(Spacer(1, 6))
            i += 1
            continue

        if i + 1 < len(lines) and "|" in line and _is_table_separator(lines[i + 1]):
            headers = _split_table_row(line)
            rows: list[list[str]] = []
            i += 2
            while i < len(lines):
                row_line = lines[i].rstrip()
                if not row_line.strip() or "|" not in row_line:
                    break
                cells = _split_table_row(row_line)
                if len(cells) != len(headers):
                    break
                rows.append(cells)
                i += 1
            story.append(_build_table_flowable(headers, rows, styles, content_width))
            story.append(Spacer(1, 8))
            continue

        if line.lstrip().startswith(">"):
            quote_lines: list[str] = []
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                quote_lines.append(re.sub(r"^\s*>\s?", "", lines[i]).rstrip())
                i += 1
            summary_text = " ".join(part for part in quote_lines if part.strip())
            box = Table(
                [[Paragraph(_safe_inline(summary_text, keep_breaks=True), styles["summary"])]],
                colWidths=[content_width],
            )
            box.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                        ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor("#60a5fa")),
                        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#dbeafe")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 10),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ]
                )
            )
            story.append(box)
            story.append(Spacer(1, 8))
            continue

        if not line.strip():
            story.append(Spacer(1, 6))
            i += 1
            continue

        if line.startswith("### "):
            story.append(Paragraph(_safe_inline(line[4:]), styles["h3"]))
            i += 1
            continue

        if line.startswith("## "):
            story.append(Paragraph(_safe_inline(line[3:]), styles["h2"]))
            i += 1
            continue

        if line.startswith("# "):
            story.append(Paragraph(_safe_inline(line[2:]), styles["h1"]))
            i += 1
            continue

        bullet_match = re.match(r"^(\s*)[-*]\s+(.*)$", line)
        if bullet_match:
            text = bullet_match.group(2)
            indent = 14 + (len(bullet_match.group(1).expandtabs(2)) // 2) * 8
            story.append(
                Paragraph(f"• {_safe_inline(text)}", _with_indent("bullet", min(indent, 84)))
            )
            i += 1
            continue

        numbered_match = re.match(r"^(\s*)\d+\.\s+.*$", line)
        if numbered_match:
            indent = (len(numbered_match.group(1).expandtabs(2)) // 2) * 8
            story.append(Paragraph(_safe_inline(line.strip()), _with_indent("body", min(indent, 84))))
            i += 1
            continue

        hierarchical_match = re.match(r"^\s*(\d+(?:\.\d+)+)\s+(.+)$", line)
        if hierarchical_match:
            depth = hierarchical_match.group(1).count(".")
            indent = depth * 10
            content = f"{hierarchical_match.group(1)} {hierarchical_match.group(2)}"
            story.append(Paragraph(_safe_inline(content), _with_indent("body", min(indent, 84))))
            i += 1
            continue

        story.append(Paragraph(_safe_inline(line.strip()), styles["body"]))
        i += 1

    if in_code and code_lines:
        story.append(Preformatted("\n".join(code_lines), styles["code"]))

    return story


def _split_quiz_sections(content_markdown: str) -> tuple[str, str | None]:
    patterns = [r"\n##\s+Answer\s+Key", r"\n##\s+Mark\s+Scheme", r"\n##\s+Solution"]
    for pattern in patterns:
        match = re.search(pattern, content_markdown, flags=re.IGNORECASE)
        if match:
            return content_markdown[: match.start()].strip(), content_markdown[match.start():].strip()
    return content_markdown, None


def render_document_pdf(
    *,
    kind: str,
    video_title: str,
    channel: str,
    youtube_url: str,
    summary: str,
    content_markdown: str,
    note_style: str | None = None,
) -> bytes:
    mind_map_drawing = None
    page_size = A4
    if kind == "notes" and note_style == "mind_map":
        mind_map_drawing = render_mind_map_drawing(content_markdown)
        if mind_map_drawing is not None:
            # Mind-map notes are intentionally not constrained to A4.
            page_size = (
                max(A4[0], float(mind_map_drawing.width) + 72),
                max(A4[1], float(mind_map_drawing.height) + 760),
            )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        leftMargin=36,
        rightMargin=36,
        topMargin=40,
        bottomMargin=40,
        title=f"{video_title} - {kind}",
    )
    styles = _build_styles()
    story: list = []

    story.append(Paragraph(f"{kind.title()} PDF", styles["title"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"Video: {html.escape(video_title, quote=False)}", styles["meta"]))
    story.append(Paragraph(f"Channel: {html.escape(channel, quote=False)}", styles["meta"]))
    story.append(Paragraph(f"URL: {html.escape(youtube_url, quote=False)}", styles["meta"]))
    story.append(Paragraph(f"Generated: {datetime.utcnow().isoformat()}Z", styles["meta"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Summary", styles["h2"]))
    safe_summary = _safe_inline(summary, keep_breaks=True)
    story.append(Paragraph(safe_summary, styles["body"]))
    story.append(Spacer(1, 12))

    if kind == "quiz":
        quiz_body, answer_key = _split_quiz_sections(content_markdown)
        story.append(Paragraph("Quiz", styles["h2"]))
        story.extend(_markdown_to_story(quiz_body, styles, doc.width))
        if answer_key:
            story.append(PageBreak())
            story.extend(_markdown_to_story(answer_key, styles, doc.width))
    else:
        story.append(Paragraph("Notes", styles["h2"]))
        if note_style == "mind_map":
            if mind_map_drawing is not None:
                story.append(mind_map_drawing)
                story.append(Spacer(1, 12))
            else:
                story.extend(_markdown_to_story(content_markdown, styles, doc.width))
        else:
            story.extend(_markdown_to_story(content_markdown, styles, doc.width))

    doc.build(story)
    return buffer.getvalue()
