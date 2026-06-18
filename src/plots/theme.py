from __future__ import annotations

MOISTURE_COLORS: dict[str, str] = {
    "dry": "#D85A30",
    "all": "darkgreen",
    "wet": "#185FA5",
}

HIGHLIGHT_COLORS: dict[str, str] = {
    "top": "#E31A1C",
    "other": "#B3B3B3",  # R grey70 equivalent
}

BASE_FONT_SIZE: int = 11
TITLE_FONT_SIZE: int = 13
SUBTITLE_FONT_SIZE: int = 10
FIGURE_WIDTH: int = 1400
FIGURE_HEIGHT: int = 600

# Qualitative palette for foreground treatment lines (Set1-inspired, no yellow)
QUALITATIVE_COLORS: list[str] = [
    "#E41A1C", "#377EB8", "#4DAF4A", "#984EA3",
    "#FF7F00", "#A65628", "#F781BF", "#17BECF",
    "#BCBD22", "#7F7F7F", "#AEC7E8", "#FFBB78",
]

_RAMP: list[str] = [
    "#2166AC", "#4DAC26", "#F7A400", "#D6604D",
    "#8B2FC9", "#A65628", "#E31A1C",
]


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: float, g: float, b: float) -> str:
    return f"#{int(round(r)):02x}{int(round(g)):02x}{int(round(b)):02x}"


def mg_colors(mg_values: list[str]) -> dict[str, str]:
    """Return a colour per MG value by interpolating a 7-stop ramp."""
    if not mg_values:
        return {}
    sorted_mgs = sorted(set(str(v) for v in mg_values))
    n = len(sorted_mgs)
    ramp_rgb = [_hex_to_rgb(h) for h in _RAMP]
    n_stops = len(ramp_rgb)
    result: dict[str, str] = {}
    for i, mg in enumerate(sorted_mgs):
        t = 0.0 if n == 1 else i / (n - 1)
        seg = min(int(t * (n_stops - 1)), n_stops - 2)
        local_t = t * (n_stops - 1) - seg
        r1, g1, b1 = ramp_rgb[seg]
        r2, g2, b2 = ramp_rgb[seg + 1]
        result[mg] = _rgb_to_hex(
            r1 + (r2 - r1) * local_t,
            g1 + (g2 - g1) * local_t,
            b1 + (b2 - b1) * local_t,
        )
    return result


def make_trt_label(row) -> str:
    """Format a treatment row as a human-readable label."""
    return f"MG{row['MG']} · {row['pop'] / 1000:.0f}k · {row['rs']}in"


def fg_colors(labels: list[str]) -> dict[str, str]:
    """Assign qualitative colours to a list of foreground treatment labels."""
    sorted_labels = sorted(set(labels))
    return {
        label: QUALITATIVE_COLORS[i % len(QUALITATIVE_COLORS)]
        for i, label in enumerate(sorted_labels)
    }
