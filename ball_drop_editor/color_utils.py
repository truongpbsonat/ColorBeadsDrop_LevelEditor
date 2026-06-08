from __future__ import annotations

from .constants import BALL_COLORS, COLOR_HEX

SELECTABLE_BALL_COLORS = tuple(color for color in BALL_COLORS if color != "None")


def color_text_hex(color: str) -> str:
    hex_color = COLOR_HEX.get(color, "#777777").lstrip("#")
    red, green, blue = (int(hex_color[index:index + 2], 16) for index in (0, 2, 4))
    brightness = (red * 299 + green * 587 + blue * 114) / 1000
    return "#000000" if brightness >= 145 else "#FFFFFF"
