"""Draws the stat panel on the HUD canvas.

Rows are laid out top to bottom; when a column reaches the bottom of the screen a new column is
started to the right. Colors are plain (R, G, B, A) tuples, applied with Canvas.SetDrawColor.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from . import reader, sdk, sources, stats

FONT_PATH = "EngineFonts.SmallFont"
BACKGROUND_TEXTURE = "EngineResources.WhiteSquareTexture"

WHITE = (255, 255, 255, 255)
HEADER = (255, 200, 60, 255)
GOOD = (110, 235, 110, 255)
BAD = (255, 100, 100, 255)
SOURCE = (190, 190, 190, 255)
WARN = (240, 220, 60, 255)

PADDING = 8
COLUMN_GAP = 24
VALUE_GAP = 18
UNEXPLAINED_TOLERANCE = 0.005


@dataclass
class Settings:
    x_percent: float
    y_percent: float
    scale_percent: float
    background_opacity: float
    only_modified: bool
    with_sources: bool


@dataclass
class Row:
    left: str
    right: str = ""
    left_color: Tuple[int, int, int, int] = WHITE
    right_color: Tuple[int, int, int, int] = WHITE
    indent: int = 0


def _value_text(reading: reader.Reading) -> Tuple[str, Tuple[int, int, int, int]]:
    stat = reading.stat
    text = stats.format_value(stat, reading.value)
    if stat.kind == stats.TIMER:
        return text, WHITE  # a countdown is neither better nor worse
    ratio = stats.change_ratio(stat, reading.value, reading.base)
    if ratio is None or abs(ratio) < 0.0005:
        return text, WHITE
    if stat.kind != stats.MULT:  # MULT already reads as a percentage
        text += "  (%+.0f%%)" % (ratio * 100)
    improved = (ratio > 0) != stat.lower_better
    return text, GOOD if improved else BAD


def _impact(reading: reader.Reading, c: reader.Contribution) -> float:
    """Rough relative effect of a contribution, to list the biggest buffs first. Scale values
    are already relative; additive ones are compared against the base / final value."""
    if c.mod_type == reader.MOD_SCALE:
        return abs(c.value)
    reference = reading.base if c.mod_type == reader.MOD_PREADD else reading.value
    return abs(c.value) / max(abs(reference), 1e-6)


def _is_modified(reading: reader.Reading) -> bool:
    if reading.stat.kind == stats.BAR:
        return reading.value > 0  # token counts never differ from their base; any token is a bonus
    if reading.stat.kind == stats.TIMER:
        return True
    return abs(reading.value - reading.base) > 1e-6 or bool(reading.contributions)


def build_rows(readings: List[reader.Reading], settings: Settings) -> List[Row]:
    rows: List[Row] = []
    group = None
    for reading in readings:
        if settings.only_modified and not _is_modified(reading):
            continue
        if reading.stat.group != group:
            group = reading.stat.group
            rows.append(Row(group, left_color=HEADER))
        right, color = _value_text(reading)
        rows.append(Row(reading.stat.label, right, right_color=color, indent=1))
        if not settings.with_sources or reading.stat.kind == stats.TIMER:
            continue
        neutral_base = reading.stat.kind == stats.MULT and reading.base == 1.0  # would read "+0.0%"
        if not neutral_base and stats.change_ratio(reading.stat, reading.value, reading.base) is not None:
            rows.append(Row("Base", stats.format_value(reading.stat, reading.base), SOURCE, SOURCE, indent=2))
        for c in sorted(reading.contributions, key=lambda c: _impact(reading, c), reverse=True):
            label = c.source if c.count == 1 else "%s  x%d" % (c.source, c.count)
            rows.append(Row(label, stats.format_modifier(reading.stat, c.mod_type, c.value), SOURCE, SOURCE, indent=2))
        if reading.predicted is not None:
            diff = reading.value - reading.predicted
            if abs(diff) > UNEXPLAINED_TOLERANCE * max(1.0, abs(reading.value)):
                rows.append(Row("unexplained", "%+.3g" % diff, WARN, WARN, indent=2))
    if not rows:
        rows.append(Row("No modified stats", left_color=SOURCE))
    return rows


# Font and texture, held as weak pointers (see sdk.ObjectCache)
_cache = sdk.ObjectCache()

# Unscaled text sizes by string. The font never changes, so a string is measured once instead of
# up to three TextSize engine calls per row per frame. Bounded: timers produce new strings
# ("4.9s", "4.8s", ...), so the oldest entries are evicted (dict insertion order) past the limit,
# rather than clearing everything and re-measuring the whole panel in one frame
_text_sizes: Dict[str, Tuple[float, float]] = {}
TEXT_SIZE_CACHE_LIMIT = 4000


def _find(cls: str, path: str) -> Optional[Any]:
    return _cache.get(cls, path)


def _text_size(canvas: Any, text: str) -> Tuple[float, float]:
    size = _text_sizes.get(text)
    if size is None:
        if len(_text_sizes) >= TEXT_SIZE_CACHE_LIMIT:
            del _text_sizes[next(iter(_text_sizes))]
        size = _text_sizes[text] = sdk.text_size(canvas, text)
    return size


def _apply_font(canvas: Any) -> None:
    font = _find("Font", FONT_PATH)
    if font is not None:
        sdk.set_font(canvas, font)
    else:
        sources.log_error_once("font", "font not found: " + FONT_PATH)


def draw(canvas: Any, rows: List[Row], settings: Settings) -> None:
    _apply_font(canvas)
    scale = settings.scale_percent / 100.0
    indent_width = _text_size(canvas, "    ")[0] * scale
    line_height = _text_size(canvas, "Ag")[1] * scale + 2

    def width(text: str) -> float:
        return _text_size(canvas, text)[0] * scale if text else 0.0

    left_width = max(width(r.left) + r.indent * indent_width for r in rows)
    right_width = max(width(r.right) for r in rows)
    column_width = PADDING * 2 + left_width + VALUE_GAP + right_width

    # Layout: split rows into columns that fit on screen
    size_x, size_y = sdk.canvas_size(canvas)
    start_x = size_x * settings.x_percent / 100.0
    start_y = size_y * settings.y_percent / 100.0
    max_rows = max(1, int((size_y - start_y - PADDING * 2) // line_height))
    columns = [rows[i:i + max_rows] for i in range(0, len(rows), max_rows)]

    for col_index, column in enumerate(columns):
        x = start_x + col_index * (column_width + COLUMN_GAP)
        _draw_background(canvas, x, start_y, column_width, len(column) * line_height + PADDING * 2, settings)
        y = start_y + PADDING
        for row in column:
            sdk.set_pos(canvas, x + PADDING + row.indent * indent_width, y)
            sdk.set_color(canvas, row.left_color)
            sdk.draw_text(canvas, row.left, scale)
            if row.right:
                sdk.set_pos(canvas, x + column_width - PADDING - width(row.right), y)
                sdk.set_color(canvas, row.right_color)
                sdk.draw_text(canvas, row.right, scale)
            y += line_height


def draw_toast(canvas: Any, text: str, settings: Settings) -> None:
    """Short notification centered near the top of the screen (mode changes and the like)."""
    _apply_font(canvas)
    scale = settings.scale_percent / 100.0 * 1.2
    width, height = (v * scale for v in _text_size(canvas, text))
    size_x, size_y = sdk.canvas_size(canvas)
    x = (size_x - width) / 2
    y = size_y * 0.08
    _draw_background(canvas, x - PADDING, y - PADDING / 2, width + PADDING * 2, height + PADDING, settings)
    sdk.set_pos(canvas, x, y)
    sdk.set_color(canvas, HEADER)
    sdk.draw_text(canvas, text, scale)


def _draw_background(canvas: Any, x: float, y: float, w: float, h: float, settings: Settings) -> None:
    if settings.background_opacity <= 0:
        return
    texture = _find("Texture2D", BACKGROUND_TEXTURE)
    if texture is None:
        sources.log_error_once("bg", "background texture not found: " + BACKGROUND_TEXTURE)
        return
    try:
        sdk.set_pos(canvas, x, y)
        sdk.set_color(canvas, (0, 0, 0, int(255 * settings.background_opacity / 100)))
        sdk.draw_rect(canvas, w, h, texture)
    except Exception as ex:
        sources.log_error_once("bg draw", "background draw failed: %s" % ex)
