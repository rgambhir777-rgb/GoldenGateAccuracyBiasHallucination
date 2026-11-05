"""Dependency-free inline SVG charts for the self-contained HTML report."""

from __future__ import annotations

from html import escape

ACCENT = "#16a34a"
THRESHOLD = "#dc2626"
GRID = "#e5e7eb"
TEXT = "#4b5563"


def line_chart(points: list[tuple[str, float | None]], title: str, threshold: float | None = None,
               percent: bool = True, width: int = 420, height: int = 210) -> str:
    """Line chart of one metric across releases, with an optional dashed threshold line."""
    pad_l, pad_r, pad_t, pad_b = 44, 16, 30, 40
    values = [v for _, v in points if v is not None]
    if not values:
        return f'<svg width="{width}" height="{height}" role="img"><text x="10" y="20">{escape(title)}: no data</text></svg>'
    lo = min(values + ([threshold] if threshold is not None else []))
    hi = max(values + ([threshold] if threshold is not None else []))
    if percent:
        lo, hi = max(0.0, lo - 0.05), min(1.0, hi + 0.05)
    if hi - lo < 1e-9:
        lo, hi = lo - 0.05, hi + 0.05
    plot_w, plot_h = width - pad_l - pad_r, height - pad_t - pad_b
    n = len(points)

    def x(i: int) -> float:
        return pad_l + (plot_w * (i / (n - 1)) if n > 1 else plot_w / 2)

    def y(v: float) -> float:
        return pad_t + plot_h * (1 - (v - lo) / (hi - lo))

    def label(v: float) -> str:
        return f"{v * 100:.0f}%" if percent else f"{v:.2f}"

    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="{escape(title)}" '
             f'style="max-width:{width}px;font-family:Inter,Segoe UI,sans-serif">',
             f'<text x="{pad_l}" y="18" font-size="13" font-weight="600" fill="#111827">{escape(title)}</text>']
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        parts.append(f'<line x1="{pad_l}" x2="{width - pad_r}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{GRID}"/>')
        parts.append(f'<text x="{pad_l - 6}" y="{y(v) + 4:.1f}" font-size="10" text-anchor="end" fill="{TEXT}">'
                     f'{label(v)}</text>')
    if threshold is not None:
        parts.append(f'<line x1="{pad_l}" x2="{width - pad_r}" y1="{y(threshold):.1f}" y2="{y(threshold):.1f}" '
                     f'stroke="{THRESHOLD}" stroke-dasharray="5 4" stroke-width="1.5"/>')
        parts.append(f'<text x="{width - pad_r}" y="{y(threshold) - 4:.1f}" font-size="10" text-anchor="end" '
                     f'fill="{THRESHOLD}">gate {label(threshold)}</text>')
    coords = [(x(i), y(v)) for i, (_, v) in enumerate(points) if v is not None]
    parts.append('<polyline fill="none" stroke="{}" stroke-width="2.5" points="{}"/>'.format(
        ACCENT, " ".join(f"{a:.1f},{b:.1f}" for a, b in coords)))
    for i, (name, v) in enumerate(points):
        parts.append(f'<text x="{x(i):.1f}" y="{height - 14}" font-size="10" text-anchor="middle" fill="{TEXT}">'
                     f'{escape(name)}</text>')
        if v is not None:
            parts.append(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="4" fill="{ACCENT}"><title>{escape(name)}: '
                         f'{label(v)}</title></circle>')
    parts.append("</svg>")
    return "".join(parts)
