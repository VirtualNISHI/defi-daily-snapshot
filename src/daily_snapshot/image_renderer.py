"""Render the daily snapshot as a 1200×720 PNG (dark theme).

Layout:
    ┌────────────────────────────────────────────────────────────┐
    │  📊  DeFi Daily Snapshot                                   │
    │      2026-05-07 (JST)                                      │
    ├────────────────────────────────────────────────────────────┤
    │  🚀  Top gainers (24h)                                     │
    │      • Aave (Lending)              $24.5B   +5.2%          │
    │      ...                                                   │
    │  📉  Top losers (24h)                                      │
    │      ...                                                   │
    │  🌐  Top chains (TVL)                                      │
    │      ...                                                   │
    ├────────────────────────────────────────────────────────────┤
    │  Auto-generated · Data via DefiLlama                       │
    └────────────────────────────────────────────────────────────┘

Emoji rendering uses ``pilmoji`` (Twemoji CDN with on-disk cache); CJK glyphs
use Yu Gothic on Windows or Noto Sans CJK on Linux.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pilmoji import Pilmoji

from .collector import SnapshotRow

log = logging.getLogger(__name__)

# Canvas — sized so 3 sections × 3 rows + header + footer pack tightly.
W, H = 1200, 720
PAD = 50

# Dark palette
BG = (14, 16, 20)              # #0e1014
CARD = (26, 29, 36)            # #1a1d24
DIVIDER = (48, 54, 61)         # #30363d
TEXT = (230, 237, 243)         # #e6edf3
DIM = (139, 148, 158)          # #8b949e
GREEN = (63, 185, 80)          # #3fb950
RED = (248, 81, 73)            # #f85149
ACCENT = (139, 148, 230)       # purple-blue accent for header

# Font candidates: tried in order; first that exists wins.
_JP_FONT_CANDIDATES = [
    ("C:/Windows/Fonts/YuGothB.ttc", 0),       # Yu Gothic Bold (Win)
    ("C:/Windows/Fonts/YuGothM.ttc", 0),       # Yu Gothic Medium (Win)
    ("C:/Windows/Fonts/meiryob.ttc", 0),       # Meiryo Bold (Win)
    ("C:/Windows/Fonts/meiryo.ttc", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0),
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0),  # macOS
]
_MONO_FONT_CANDIDATES = [
    ("C:/Windows/Fonts/consolab.ttf", 0),       # Consolas Bold
    ("C:/Windows/Fonts/consola.ttf", 0),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 0),
]


def _load_font(candidates: list[tuple[str, int]], size: int) -> ImageFont.FreeTypeFont:
    """Return the first font that loads. Raises if none found."""
    for path, index in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size, index=index)
            except OSError as exc:
                log.debug("font %s failed: %s", path, exc)
                continue
    raise RuntimeError(
        "No usable font found. Install fonts-noto-cjk on Linux or use Windows."
    )


def _fmt_value(v: float | None) -> str:
    """Format a TVL/USD value with B/M/K suffix: 24_500_000_000 → '$24.5B'."""
    if v is None:
        return "—"
    av = abs(v)
    if av >= 1e12:
        return f"${v / 1e12:.2f}T"
    if av >= 1e9:
        return f"${v / 1e9:.1f}B"
    if av >= 1e6:
        return f"${v / 1e6:.1f}M"
    if av >= 1e3:
        return f"${v / 1e3:.1f}K"
    return f"${v:.0f}"


def _fmt_delta_pct(d: float | None) -> tuple[str, tuple[int, int, int]]:
    """Return (text, color) for a 24h % change. Fraction in → '+5.2%' out.
    Returns ('—', DIM) when ``d`` is None (e.g. for chain rows)."""
    if d is None:
        return "—", DIM
    pct = d * 100
    sign = "+" if pct >= 0 else ""
    color = GREEN if pct >= 0 else RED
    return f"{sign}{pct:.2f}%", color


def _label(row: SnapshotRow, aliases: dict[str, str], max_chars: int = 28) -> str:
    if row.slug and row.slug in aliases:
        return aliases[row.slug]
    q = row.question or "(unknown)"
    return q if len(q) <= max_chars else q[: max_chars - 1].rstrip() + "…"


def render_snapshot_png(
    *,
    snapshot_date: datetime,
    gainers: list[SnapshotRow],
    losers: list[SnapshotRow],
    chains: list[SnapshotRow],
    aliases: dict[str, str],
) -> bytes:
    """Render the snapshot to PNG bytes."""
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    title_font = _load_font(_JP_FONT_CANDIDATES, 36)
    date_font = _load_font(_JP_FONT_CANDIDATES, 22)
    section_font = _load_font(_JP_FONT_CANDIDATES, 24)
    label_font = _load_font(_JP_FONT_CANDIDATES, 20)
    value_font = _load_font(_MONO_FONT_CANDIDATES, 22)
    footer_font = _load_font(_JP_FONT_CANDIDATES, 16)

    with Pilmoji(img) as pilmoji:
        # ---------- Header ----------
        date_str = snapshot_date.strftime("%Y-%m-%d")
        pilmoji.text(
            (PAD, 36),
            "📊  DeFi Daily Snapshot",
            font=title_font,
            fill=TEXT,
        )
        draw.text(
            (PAD, 84),
            f"{date_str} (JST)",
            font=date_font,
            fill=DIM,
        )
        # Header divider
        draw.line(
            [(PAD, 130), (W - PAD, 130)],
            fill=DIVIDER,
            width=2,
        )

        # ---------- Sections ----------
        sections: list[tuple[str, str, list[SnapshotRow]]] = [
            ("🚀", "Top gainers (24h)", gainers),
            ("📉", "Top losers (24h)", losers),
            ("🌐", "Top chains (TVL)", chains),
        ]

        y = 160
        for emoji, title, rows in sections:
            # Section title with emoji
            pilmoji.text(
                (PAD, y),
                f"{emoji}  {title}",
                font=section_font,
                fill=TEXT,
            )
            y += 42

            for r in rows:
                label = _label(r, aliases)
                value = _fmt_value(r.yes_price)
                delta_text, delta_color = _fmt_delta_pct(r.one_day_change)

                # bullet
                draw.ellipse(
                    [(PAD + 12, y + 11), (PAD + 18, y + 17)],
                    fill=DIM,
                )

                # label (left-aligned, after bullet)
                draw.text(
                    (PAD + 32, y),
                    label,
                    font=label_font,
                    fill=TEXT,
                )

                # value + delta right-aligned at fixed right edges
                delta_right = 1080
                value_right = 940

                delta_w = int(value_font.getlength(delta_text))
                value_w = int(value_font.getlength(value))

                draw.text(
                    (value_right - value_w, y),
                    value,
                    font=value_font,
                    fill=TEXT,
                )
                draw.text(
                    (delta_right - delta_w, y),
                    delta_text,
                    font=value_font,
                    fill=delta_color,
                )

                y += 32

            y += 18  # gap between sections

        # ---------- Footer ----------
        footer_y = H - 40
        draw.line(
            [(PAD, footer_y - 14), (W - PAD, footer_y - 14)],
            fill=DIVIDER,
            width=1,
        )
        draw.text(
            (PAD, footer_y),
            "Auto-generated 3×/day · Data via DefiLlama public API",
            font=footer_font,
            fill=DIM,
        )

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
