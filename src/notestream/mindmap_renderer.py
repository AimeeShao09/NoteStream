from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors


@dataclass
class MindMapNode:
    title: str
    children: list["MindMapNode"] = field(default_factory=list)


@dataclass
class PositionedNode:
    node_id: int
    title: str
    lines: list[str]
    depth: int
    x: float
    y: float
    width: float
    height: float


@dataclass
class MindMapLayout:
    width: float
    height: float
    nodes: list[PositionedNode]
    edges: list[tuple[int, int]]


@dataclass
class _RenderNode:
    node_id: int
    title: str
    depth: int
    children: list["_RenderNode"] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    width: float = 0.0
    height: float = 0.0
    x: float = 0.0
    y: float = 0.0


_BULLET_RE = re.compile(r"^(\s*)[-*]\s+(.*)$")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$")

# Large step values intentionally prioritize collision-free layout over compactness.
H_STEP = 420.0
V_GAP = 26.0
TOP_LEVEL_GAP = 48.0
MARGIN = 130.0
MIN_NODE_WIDTH = 135.0
MAX_NODE_WIDTH = 360.0
LINE_HEIGHT = 16.0
NODE_PADDING_X = 28.0
NODE_PADDING_Y = 14.0


def _clean_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", cleaned)
    cleaned = cleaned.replace("`", "")
    cleaned = cleaned.replace("**", "")
    cleaned = cleaned.replace("__", "")
    cleaned = cleaned.replace("*", "")
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _wrap_text(text: str, max_chars: int = 22) -> list[str]:
    text = text.strip()
    if not text:
        return [""]

    # CJK-like text may not contain spaces.
    if " " not in text and len(text) > max_chars:
        chunks = [text[idx : idx + max_chars] for idx in range(0, len(text), max_chars)]
        return chunks[:6]

    words = text.split()
    lines: list[str] = []
    current = ""

    for word in words:
        if len(word) > max_chars:
            if current:
                lines.append(current)
                current = ""
            for idx in range(0, len(word), max_chars):
                lines.append(word[idx : idx + max_chars])
            continue

        if not current:
            current = word
            continue

        candidate = f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines[:6]


def parse_mind_map_markdown(markdown: str) -> MindMapNode | None:
    heading_title: str | None = None
    bullets: list[tuple[int, str]] = []

    for raw_line in markdown.splitlines():
        heading_match = _HEADING_RE.match(raw_line.strip())
        if heading_match and not heading_title:
            heading_title = _clean_text(heading_match.group(1))

        bullet_match = _BULLET_RE.match(raw_line)
        if not bullet_match:
            continue

        indent = len(bullet_match.group(1).expandtabs(2))
        text = _clean_text(bullet_match.group(2))
        if text:
            bullets.append((indent, text))

    if not bullets:
        return None

    min_indent = min(indent for indent, _ in bullets)
    normalized = [((indent - min_indent) // 2, text) for indent, text in bullets]

    pseudo_root = MindMapNode("__pseudo__")
    stack: list[tuple[int, MindMapNode]] = [(-1, pseudo_root)]

    for depth, text in normalized:
        node = MindMapNode(text)
        while len(stack) > 1 and depth <= stack[-1][0]:
            stack.pop()
        stack[-1][1].children.append(node)
        stack.append((depth, node))

    if len(pseudo_root.children) == 1:
        return pseudo_root.children[0]

    return MindMapNode(heading_title or "Mind Map", children=pseudo_root.children)


def _decorate_tree(node: MindMapNode) -> _RenderNode:
    counter = {"id": 0}

    def visit(current: MindMapNode, depth: int) -> _RenderNode:
        node_id = counter["id"]
        counter["id"] += 1

        wrapped = _wrap_text(current.title, max_chars=max(14, 24 - depth))
        text_width = max((len(line) for line in wrapped), default=0) * 6.8
        width = max(MIN_NODE_WIDTH, min(MAX_NODE_WIDTH, text_width + NODE_PADDING_X))
        height = max(40.0, NODE_PADDING_Y + len(wrapped) * LINE_HEIGHT)

        out = _RenderNode(
            node_id=node_id,
            title=current.title,
            depth=depth,
            lines=wrapped,
            width=width,
            height=height,
        )
        out.children = [visit(child, depth + 1) for child in current.children]
        return out

    return visit(node, 0)


def _leaf_count(node: _RenderNode) -> int:
    if not node.children:
        return 1
    return sum(_leaf_count(child) for child in node.children)


def _subtree_height(node: _RenderNode) -> float:
    if not node.children:
        return node.height
    children_height = sum(_subtree_height(child) for child in node.children)
    children_height += V_GAP * (len(node.children) - 1)
    return max(node.height, children_height)


def _split_top_level_children(children: list[_RenderNode]) -> tuple[list[_RenderNode], list[_RenderNode]]:
    left: list[_RenderNode] = []
    right: list[_RenderNode] = []
    left_height = 0.0
    right_height = 0.0

    for child in children:
        h = _subtree_height(child)
        if left_height <= right_height:
            left.append(child)
            left_height += h
        else:
            right.append(child)
            right_height += h

    if not left:
        left, right = right[:1], right[1:]
    if not right:
        right, left = left[:1], left[1:]

    return left, right


def _place_subtree(node: _RenderNode, *, side: int, depth: int, center_y: float) -> None:
    node.x = side * depth * H_STEP

    if not node.children:
        node.y = center_y
        return

    total = sum(_subtree_height(child) for child in node.children)
    total += V_GAP * (len(node.children) - 1)
    start = center_y - total / 2.0

    child_centers: list[float] = []
    for child in node.children:
        child_height = _subtree_height(child)
        child_center = start + child_height / 2.0
        _place_subtree(child, side=side, depth=depth + 1, center_y=child_center)
        child_centers.append(child.y)
        start += child_height + V_GAP

    node.y = sum(child_centers) / len(child_centers)


def _collect_nodes(root: _RenderNode) -> tuple[list[PositionedNode], list[tuple[int, int]]]:
    nodes: list[PositionedNode] = []
    edges: list[tuple[int, int]] = []

    def dfs(node: _RenderNode) -> None:
        nodes.append(
            PositionedNode(
                node_id=node.node_id,
                title=node.title,
                lines=node.lines,
                depth=node.depth,
                x=node.x,
                y=node.y,
                width=node.width,
                height=node.height,
            )
        )
        for child in node.children:
            edges.append((node.node_id, child.node_id))
            dfs(child)

    dfs(root)
    return nodes, edges


def _normalize_bounds(nodes: list[PositionedNode]) -> tuple[float, float]:
    min_x = min(node.x - node.width / 2.0 for node in nodes)
    max_x = max(node.x + node.width / 2.0 for node in nodes)
    min_y = min(node.y - node.height / 2.0 for node in nodes)
    max_y = max(node.y + node.height / 2.0 for node in nodes)

    shift_x = MARGIN - min_x
    shift_y = MARGIN - min_y

    for node in nodes:
        node.x += shift_x
        node.y += shift_y

    width = (max_x - min_x) + MARGIN * 2.0
    height = (max_y - min_y) + MARGIN * 2.0
    return width, height


def _compute_layout(root_node: MindMapNode) -> MindMapLayout:
    root = _decorate_tree(root_node)
    root.x = 0.0
    root.y = 0.0

    if root.children:
        left_children, right_children = _split_top_level_children(root.children)

        def place_side(children: list[_RenderNode], side: int) -> None:
            if not children:
                return
            total = sum(_subtree_height(child) for child in children)
            total += TOP_LEVEL_GAP * (len(children) - 1)
            start = -total / 2.0
            for child in children:
                child_h = _subtree_height(child)
                center = start + child_h / 2.0
                _place_subtree(child, side=side, depth=1, center_y=center)
                start += child_h + TOP_LEVEL_GAP

        place_side(left_children, side=-1)
        place_side(right_children, side=1)

    nodes, edges = _collect_nodes(root)
    width, height = _normalize_bounds(nodes)

    return MindMapLayout(width=width, height=height, nodes=nodes, edges=edges)


def _palette(depth: int) -> tuple[str, str]:
    fills = [
        "#dbeafe",
        "#e2e8f0",
        "#fef3c7",
        "#dcfce7",
        "#fee2e2",
        "#ede9fe",
    ]
    strokes = [
        "#1d4ed8",
        "#334155",
        "#b45309",
        "#166534",
        "#b91c1c",
        "#6d28d9",
    ]
    idx = min(depth, len(fills) - 1)
    return fills[idx], strokes[idx]


def render_mind_map_svg(markdown: str) -> str | None:
    root = parse_mind_map_markdown(markdown)
    if root is None:
        return None

    layout = _compute_layout(root)
    by_id = {node.node_id: node for node in layout.nodes}

    parts: list[str] = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {int(layout.width)} {int(layout.height)}" '
            f'width="{int(layout.width)}" height="{int(layout.height)}" role="img" '
            f'aria-label="Mind map diagram">'
        ),
        '<rect x="0" y="0" width="100%" height="100%" fill="#f8fafc"/>',
    ]

    for parent_id, child_id in layout.edges:
        parent = by_id[parent_id]
        child = by_id[child_id]
        parts.append(
            (
                f'<line x1="{parent.x:.2f}" y1="{parent.y:.2f}" '
                f'x2="{child.x:.2f}" y2="{child.y:.2f}" '
                'stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round"/>'
            )
        )

    for node in layout.nodes:
        fill, stroke = _palette(node.depth)
        x = node.x - node.width / 2.0
        y = node.y - node.height / 2.0
        parts.append(
            (
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{node.width:.2f}" '
                f'height="{node.height:.2f}" rx="11" ry="11" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
            )
        )

        base_y = node.y - ((len(node.lines) - 1) * (LINE_HEIGHT / 2.0))
        parts.append(
            (
                f'<text x="{node.x:.2f}" y="{base_y:.2f}" '
                'font-family="Arial, sans-serif" font-size="12" '
                'text-anchor="middle" fill="#0f172a">'
            )
        )
        for idx, line in enumerate(node.lines):
            dy = 0 if idx == 0 else LINE_HEIGHT
            parts.append(
                f'<tspan x="{node.x:.2f}" dy="{dy}">{html.escape(line, quote=False)}</tspan>'
            )
        parts.append("</text>")

    parts.append("</svg>")
    return "".join(parts)


def render_mind_map_drawing(
    markdown: str,
    *,
    max_width: float | None = None,
    max_height: float | None = None,
) -> Drawing | None:
    root = parse_mind_map_markdown(markdown)
    if root is None:
        return None

    layout = _compute_layout(root)
    by_id = {node.node_id: node for node in layout.nodes}

    drawing = Drawing(layout.width, layout.height)

    for parent_id, child_id in layout.edges:
        parent = by_id[parent_id]
        child = by_id[child_id]
        line = Line(parent.x, layout.height - parent.y, child.x, layout.height - child.y)
        line.strokeColor = colors.HexColor("#94a3b8")
        line.strokeWidth = 1.6
        drawing.add(line)

    for node in layout.nodes:
        fill, stroke = _palette(node.depth)
        x = node.x - node.width / 2.0
        y_bottom = layout.height - (node.y + node.height / 2.0)

        box = Rect(x, y_bottom, node.width, node.height, rx=11, ry=11)
        box.fillColor = colors.HexColor(fill)
        box.strokeColor = colors.HexColor(stroke)
        box.strokeWidth = 1.2
        drawing.add(box)

        base_svg_y = node.y - ((len(node.lines) - 1) * (LINE_HEIGHT / 2.0))
        for idx, text in enumerate(node.lines):
            y_svg = base_svg_y + idx * LINE_HEIGHT
            y_pdf = layout.height - y_svg - 4
            label = String(
                node.x,
                y_pdf,
                text,
                textAnchor="middle",
                fontName="Helvetica",
                fontSize=10,
                fillColor=colors.HexColor("#0f172a"),
            )
            drawing.add(label)

    if max_width or max_height:
        factors = [1.0]
        if max_width:
            factors.append(max_width / drawing.width)
        if max_height:
            factors.append(max_height / drawing.height)
        scale = min(factors)
        if scale < 1:
            drawing.scale(scale, scale)
            drawing.width *= scale
            drawing.height *= scale

    return drawing
