"""확정적 2D 도면 PNG. 박스·판재는 제3각법 3면도, 원기둥은 정면 중앙·기장 가로."""

from __future__ import annotations

import io
import math
from datetime import date

from PIL import Image, ImageDraw, ImageFont

from spec_schema import CylinderStep, Feature, SpecDraft, cylinder_steps_of, format_diameter_label, solid_extents

DRAWING_VERSION = "dim-spread-v6"

PAGE_W, PAGE_H = 1754, 1240
MARGIN = 56
TITLE_H = 88
VIEW_GAP = 72
BLACK = (13, 13, 13)
GRAY = (110, 110, 128)
GRID = (240, 240, 242)
LINE = 2
THIN = 1
EXT_GAP = 6
EXT_PAST = 5
DIM_OFF = 32
DIM_OFF2 = 64
SCALE_CHOICES = (1, 2, 5, 10)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        r"C:\Windows\Fonts\malgun.ttf",
        r"C:\Windows\Fonts\malgunbd.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansKR-Regular.otf",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def _centerline(draw: ImageDraw.ImageDraw, a: tuple[float, float], b: tuple[float, float]) -> None:
    x0, y0 = a
    x1, y1 = b
    length = math.hypot(x1 - x0, y1 - y0) or 1
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    pos = 0.0
    pattern = (14, 5, 4, 5)
    i = 0
    while pos < length:
        step = pattern[i % 4]
        nxt = min(pos + step, length)
        if i % 2 == 0:
            draw.line(
                (x0 + ux * pos, y0 + uy * pos, x0 + ux * nxt, y0 + uy * nxt),
                fill=GRAY,
                width=THIN,
            )
        pos = nxt
        i += 1


class _LabelAvoid:
    """이미 그린 치수 글자와 겹치지 않게 다음 라벨을 밀어 둔다."""

    def __init__(self) -> None:
        self.boxes: list[tuple[float, float, float, float]] = []

    def _hits(self, box: tuple[float, float, float, float], pad: float = 10) -> bool:
        l, t, r, b = box
        for ol, ot, orr, ob in self.boxes:
            if l < orr + pad and r + pad > ol and t < ob + pad and b + pad > ot:
                return True
        return False

    def draw(
        self,
        draw: ImageDraw.ImageDraw,
        font: ImageFont.ImageFont,
        text: str,
        x: float,
        y: float,
        align: str = "left",
    ) -> None:
        tw, th = _text_size(draw, text, font)
        if align == "center":
            x -= tw / 2
        elif align == "right":
            x -= tw
        shifts = [(0, 0)]
        for dist in (22, 36, 50, 66, 82, 98, 114, 130):
            shifts.extend(((0, -dist), (0, dist), (14, -dist), (14, dist), (28, 0), (-14, -dist), (-14, dist)))
        chosen: tuple[float, float] | None = None
        for dx, dy in shifts:
            nx, ny = x + dx, y + dy
            box = (nx - 4, ny - 3, nx + tw + 4, ny + th + 3)
            if box[0] < 28 or box[1] < 28 or box[2] > PAGE_W - 28 or box[3] > PAGE_H - 28:
                continue
            if not self._hits(box):
                chosen = (nx, ny)
                break
        if chosen is None:
            chosen = (min(max(x, 32), PAGE_W - tw - 32), min(max(y, 32), PAGE_H - th - 32))
        nx, ny = chosen
        box = (nx - 4, ny - 3, nx + tw + 4, ny + th + 3)
        draw.rectangle(box, fill=(255, 255, 255))
        draw.text((nx, ny), text, font=font, fill=BLACK)
        self.boxes.append(box)


def _arrow(draw: ImageDraw.ImageDraw, tip: tuple[float, float], tail: tuple[float, float]) -> None:
    tx, ty = tip
    ax, ay = tail
    ang = math.atan2(ty - ay, tx - ax)
    size = 7
    left = (tx - size * math.cos(ang - 0.38), ty - size * math.sin(ang - 0.38))
    right = (tx - size * math.cos(ang + 0.38), ty - size * math.sin(ang + 0.38))
    draw.polygon([tip, left, right], fill=BLACK)


def _dim_width(
    draw: ImageDraw.ImageDraw,
    x0: float,
    x1: float,
    y_edge: float,
    offset: float,
    label: str,
    font: ImageFont.ImageFont,
    below: bool = True,
    avoid: _LabelAvoid | None = None,
) -> None:
    if x1 < x0:
        x0, x1 = x1, x0
    y_dim = y_edge + offset if below else y_edge - offset
    if below:
        ey0, ey1 = y_edge + EXT_GAP, y_dim + EXT_PAST
    else:
        ey0, ey1 = y_edge - EXT_GAP, y_dim - EXT_PAST
    draw.line((x0, ey0, x0, ey1), fill=BLACK, width=THIN)
    draw.line((x1, ey0, x1, ey1), fill=BLACK, width=THIN)
    draw.line((x0, y_dim, x1, y_dim), fill=BLACK, width=THIN)
    span = x1 - x0
    if span < 36:
        _arrow(draw, (x0, y_dim), (x0 - 14, y_dim))
        _arrow(draw, (x1, y_dim), (x1 + 14, y_dim))
    else:
        _arrow(draw, (x0, y_dim), (x0 + 14, y_dim))
        _arrow(draw, (x1, y_dim), (x1 - 14, y_dim))
    tw, th = _text_size(draw, label, font)
    if tw + 10 > span:
        px, py, align = x1 + 10, y_dim - th / 2, "left"
    else:
        px = (x0 + x1) / 2
        py = y_dim - th - 8 if below else y_dim + 6
        align = "center"
    if avoid:
        avoid.draw(draw, font, label, px, py, align=align)
        return
    tx = px if align == "left" else px - tw / 2
    draw.rectangle((tx - 2, py - 1, tx + tw + 2, py + th + 1), fill=(255, 255, 255))
    draw.text((tx, py), label, font=font, fill=BLACK)


def _dim_height(
    draw: ImageDraw.ImageDraw,
    y0: float,
    y1: float,
    x_edge: float,
    offset: float,
    label: str,
    font: ImageFont.ImageFont,
    right: bool = True,
    avoid: _LabelAvoid | None = None,
    label_dy: float = 0,
) -> None:
    if y1 < y0:
        y0, y1 = y1, y0
    x_dim = x_edge + offset if right else x_edge - offset
    if right:
        ex0, ex1 = x_edge + EXT_GAP, x_dim + EXT_PAST
    else:
        ex0, ex1 = x_edge - EXT_GAP, x_dim - EXT_PAST
    draw.line((ex0, y0, ex1, y0), fill=BLACK, width=THIN)
    draw.line((ex0, y1, ex1, y1), fill=BLACK, width=THIN)
    draw.line((x_dim, y0, x_dim, y1), fill=BLACK, width=THIN)
    span = y1 - y0
    if span < 36:
        _arrow(draw, (x_dim, y0), (x_dim, y0 - 14))
        _arrow(draw, (x_dim, y1), (x_dim, y1 + 14))
    else:
        _arrow(draw, (x_dim, y0), (x_dim, y0 + 14))
        _arrow(draw, (x_dim, y1), (x_dim, y1 - 14))
    tw, th = _text_size(draw, label, font)
    px = x_dim + 8 if right else x_dim - 8
    py = (y0 + y1) / 2 - th / 2 + label_dy
    align = "left" if right else "right"
    if avoid:
        avoid.draw(draw, font, label, px, py, align=align)
        return
    tx = px if align == "left" else px - tw
    draw.rectangle((tx - 2, py - 1, tx + tw + 2, py + th + 1), fill=(255, 255, 255))
    draw.text((tx, py), label, font=font, fill=BLACK)


def _rect(draw: ImageDraw.ImageDraw, x: float, y: float, w: float, h: float) -> None:
    draw.rectangle((x, y, x + w, y + h), outline=BLACK, width=LINE)


def _circle(draw: ImageDraw.ImageDraw, cx: float, cy: float, d: float) -> None:
    r = d / 2
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=BLACK, width=LINE)


def _dashed(draw: ImageDraw.ImageDraw, a: tuple[float, float], b: tuple[float, float], dash: int = 8, gap: int = 6) -> None:
    x0, y0 = a
    x1, y1 = b
    length = math.hypot(x1 - x0, y1 - y0) or 1
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    pos = 0.0
    on = True
    while pos < length:
        step = dash if on else gap
        nxt = min(pos + step, length)
        if on:
            draw.line(
                (x0 + ux * pos, y0 + uy * pos, x0 + ux * nxt, y0 + uy * nxt),
                fill=BLACK,
                width=THIN,
            )
        pos = nxt
        on = not on


def _snap_scale(content_w: float, content_h: float, avail_w: float, avail_h: float) -> tuple[float, int]:
    px_per_mm_full = 150 / 25.4
    chosen = SCALE_CHOICES[-1]
    for n in SCALE_CHOICES:
        s = px_per_mm_full / n
        if content_w * s <= avail_w and content_h * s <= avail_h:
            chosen = n
            break
    scale = px_per_mm_full / chosen
    if content_w * scale > avail_w or content_h * scale > avail_h:
        scale = min(avail_w / content_w, avail_h / content_h)
    return scale, chosen


def _fmt(value: float) -> str:
    return f"{value:g}"


def _grid(draw: ImageDraw.ImageDraw) -> None:
    step = 20
    for x in range(step, PAGE_W, step):
        draw.line((x, 0, x, PAGE_H), fill=GRID, width=1)
    for y in range(step, PAGE_H, step):
        draw.line((0, y, PAGE_W, y), fill=GRID, width=1)


def _titleblock(
    draw: ImageDraw.ImageDraw,
    spec: SpecDraft,
    scale_n: int,
    font: ImageFont.ImageFont,
    small: ImageFont.ImageFont,
) -> None:
    x0, y0 = PAGE_W - MARGIN - 420, PAGE_H - MARGIN - TITLE_H
    x1, y1 = PAGE_W - MARGIN, PAGE_H - MARGIN
    draw.rectangle((x0, y0, x1, y1), outline=BLACK, width=LINE, fill=(255, 255, 255))
    draw.line((x0, y0 + 28, x1, y0 + 28), fill=BLACK, width=THIN)
    draw.line((x0 + 210, y0 + 28, x0 + 210, y1), fill=BLACK, width=THIN)
    title = spec.meta.title or "무제"
    purpose = spec.meta.purpose or "-"
    draw.text((x0 + 8, y0 + 6), f"품명  {title}", font=font, fill=BLACK)
    draw.text((x0 + 8, y0 + 36), f"용도  {purpose}", font=small, fill=BLACK)
    draw.text((x0 + 218, y0 + 36), "단위  mm", font=small, fill=BLACK)
    draw.text((x0 + 8, y0 + 60), f"축척  1:{scale_n}", font=small, fill=BLACK)
    draw.text((x0 + 218, y0 + 60), f"일자  {date.today().isoformat()}", font=small, fill=BLACK)
    draw.text((MARGIN, PAGE_H - MARGIN - 18), "교육용 근사 도면 (KS 완전 규격 아님)", font=small, fill=GRAY)


def _label_view(draw: ImageDraw.ImageDraw, x: float, y: float, text: str, font: ImageFont.ImageFont) -> None:
    draw.text((x, y - 22), text, font=font, fill=GRAY)


def _holes(
    draw: ImageDraw.ImageDraw,
    features: list[Feature],
    face: str,
    origin: tuple[float, float],
    size: tuple[float, float],
    default_uv: tuple[float, float],
    scale: float,
) -> None:
    ox, oy = origin
    fw, fh = size
    for feat in features:
        if feat.type != "hole" or feat.face != face:
            continue
        dia = float(feat.diameter or 0) * scale
        if dia <= 0:
            continue
        u = float(feat.center.u if feat.center.u is not None else default_uv[0]) * scale
        v = float(feat.center.v if feat.center.v is not None else default_uv[1]) * scale
        cx, cy = ox + u, oy + fh - v
        _circle(draw, cx, cy, dia)
        _centerline(draw, (cx, cy - dia / 2 - 8), (cx, cy + dia / 2 + 8))
        _centerline(draw, (cx - dia / 2 - 8, cy), (cx + dia / 2 + 8, cy))


def _draw_three_view(
    draw: ImageDraw.ImageDraw,
    spec: SpecDraft,
    s: float,
    area: tuple[float, float, float, float],
    font: ImageFont.ImageFont,
) -> None:
    w, d, h = solid_extents(spec)
    fw, fh, tw = w * s, h * s, d * s
    ax, ay, aw, ah = area
    group_w = fw + VIEW_GAP + tw
    group_h = tw + VIEW_GAP + fh
    ox = ax + (aw - group_w) / 2
    oy = ay + (ah - group_h) / 2
    top = (ox, oy)
    front = (ox, oy + tw + VIEW_GAP)
    right = (ox + fw + VIEW_GAP, oy + tw + VIEW_GAP)

    _label_view(draw, front[0], front[1], "정면도", font)
    _label_view(draw, top[0], top[1], "평면도", font)
    _label_view(draw, right[0], right[1], "우측면도", font)
    _rect(draw, *front, fw, fh)
    _rect(draw, *top, fw, tw)
    _rect(draw, *right, tw, fh)

    _holes(draw, spec.features, "front", front, (fw, fh), (w / 2, h / 2), s)
    _holes(draw, spec.features, "top", top, (fw, tw), (w / 2, d / 2), s)
    _holes(draw, spec.features, "right", right, (tw, fh), (d / 2, h / 2), s)

    avoid = _LabelAvoid()
    _dim_width(draw, front[0], front[0] + fw, front[1] + fh, DIM_OFF, _fmt(w), font, below=True, avoid=avoid)
    _dim_height(draw, front[1], front[1] + fh, front[0], DIM_OFF, _fmt(h), font, right=False, avoid=avoid)
    _dim_width(draw, top[0], top[0] + fw, top[1], DIM_OFF, _fmt(w), font, below=False, avoid=avoid)
    _dim_height(draw, top[1], top[1] + tw, top[0], DIM_OFF, _fmt(d), font, right=False, avoid=avoid)
    _dim_width(draw, right[0], right[0] + tw, right[1] + fh, DIM_OFF, _fmt(d), font, below=True, avoid=avoid)
    _dim_height(draw, right[1], right[1] + fh, right[0] + tw, DIM_OFF, _fmt(h), font, right=True, avoid=avoid)


def _draw_cylinder_front(
    draw: ImageDraw.ImageDraw,
    spec: SpecDraft,
    s: float,
    area: tuple[float, float, float, float],
    font: ImageFont.ImageFont,
) -> None:
    """기장(축)이 가로가 되도록 정면도를 눕혀 그린다."""
    steps = cylinder_steps_of(spec)
    max_od = max((float(step.outer_diameter or 0) for step in steps), default=1.0) or 1.0
    total_len = sum(float(step.length or 0) for step in steps) or 1.0
    fw, fh = total_len * s, max_od * s
    ax, ay, aw, ah = area
    ox = ax + (aw - fw) / 2
    oy = ay + (ah - fh) / 2
    _label_view(draw, ox, oy, "정면도", font)

    x = ox
    boxes: list[tuple[float, float, float, float, float, float, float, CylinderStep]] = []
    for step in steps:
        od = max(float(step.outer_diameter or 0), 1.0)
        inner = float(step.inner_diameter or 0)
        length = max(float(step.length or 0), 1.0)
        rw, rh = length * s, od * s
        y = oy + (fh - rh) / 2
        _rect(draw, x, y, rw, rh)
        if inner > 0:
            ih = inner * s
            iy = oy + (fh - ih) / 2
            _dashed(draw, (x, iy), (x + rw, iy))
            _dashed(draw, (x, iy + ih), (x + rw, iy + ih))
        boxes.append((x, y, rw, rh, od, inner, length, step))
        x += rw

    cy = oy + fh / 2
    _centerline(draw, (ox - 10, cy), (ox + fw + 8, cy))
    _holes(draw, spec.features, "front", (ox, oy), (fw, fh), (total_len / 2, max_od / 2), s)

    avoid = _LabelAvoid()
    y_bottom = oy + fh
    y_top = oy
    if len(boxes) > 1:
        for index, (sx, _sy, rw, _rh, _od, _inner, length, _step) in enumerate(boxes):
            below = index % 2 == 0
            _dim_width(
                draw,
                sx,
                sx + rw,
                y_bottom if below else y_top,
                DIM_OFF,
                _fmt(length),
                font,
                below=below,
                avoid=avoid,
            )
        _dim_width(draw, ox, ox + fw, y_bottom, DIM_OFF2, _fmt(total_len), font, below=True, avoid=avoid)
    else:
        _dim_width(draw, ox, ox + fw, y_bottom, DIM_OFF, _fmt(total_len), font, below=True, avoid=avoid)

    seen_od: set[tuple[float, str]] = set()
    seen_id: set[tuple[float, str]] = set()
    for index, (sx, _sy, rw, rh, od, inner, _ln, step) in enumerate(boxes):
        outer_label = format_diameter_label(
            od,
            getattr(step, "outer_tol_plus", None),
            getattr(step, "outer_tol_minus", None),
        )
        inner_label = (
            format_diameter_label(
                inner,
                getattr(step, "inner_tol_plus", None),
                getattr(step, "inner_tol_minus", None),
            )
            if inner > 0
            else ""
        )
        if len(boxes) == 1:
            use_right = True
            x_edge = ox + fw
        elif index == 0:
            use_right = False
            x_edge = ox
        else:
            use_right = True
            x_edge = ox + fw
        y0 = oy + (fh - od * s) / 2
        od_key = (od, outer_label)
        if od_key not in seen_od:
            seen_od.add(od_key)
            _dim_height(
                draw,
                y0,
                y0 + od * s,
                x_edge,
                DIM_OFF,
                outer_label,
                font,
                right=use_right,
                avoid=avoid,
            )
        if inner > 0:
            id_key = (inner, inner_label)
            if id_key in seen_id:
                continue
            seen_id.add(id_key)
            iy0 = oy + (fh - inner * s) / 2
            if len(boxes) == 1:
                inner_right = False
                inner_edge = ox
                inner_off = DIM_OFF
            else:
                inner_right = use_right
                inner_edge = x_edge
                inner_off = DIM_OFF2
            _dim_height(
                draw,
                iy0,
                iy0 + inner * s,
                inner_edge,
                inner_off,
                inner_label,
                font,
                right=inner_right,
                avoid=avoid,
            )


def render_drawing_png(spec: SpecDraft) -> bytes:
    image = Image.new("RGB", (PAGE_W, PAGE_H), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    font = _font(16)
    small = _font(14)

    _grid(draw)
    draw.rectangle((24, 24, PAGE_W - 24, PAGE_H - 24), outline=BLACK, width=THIN)

    area = (
        MARGIN + 40,
        MARGIN + 36,
        PAGE_W - 2 * MARGIN - 80,
        PAGE_H - 2 * MARGIN - TITLE_H - 56,
    )
    dim_pad = 96

    if spec.solid.type == "cylinder":
        diameter, _, height = solid_extents(spec)
        extra_w = 80
        extra_h = 80 if len(cylinder_steps_of(spec)) > 1 else 40
        scale, scale_n = _snap_scale(
            height,
            diameter,
            area[2] - dim_pad * 2 - extra_w,
            area[3] - dim_pad * 2 - extra_h,
        )
        _draw_cylinder_front(draw, spec, scale, area, small)
    else:
        w, d, h = solid_extents(spec)
        scale, scale_n = _snap_scale(
            w + d,
            d + h,
            area[2] - VIEW_GAP - dim_pad * 2 - 40,
            area[3] - VIEW_GAP - dim_pad * 2 - 40,
        )
        _draw_three_view(draw, spec, scale, area, small)

    _titleblock(draw, spec, scale_n, font, small)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
