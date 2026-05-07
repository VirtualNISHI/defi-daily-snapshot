"""Format the snapshot for Discord (rich embed) and X (280-char tweet).

Display labels: each row is rendered with a short label. By default we
truncate ``question`` to ``label_max_chars`` characters; ``display_aliases``
({slug: short_label}) lets the operator override per-row labels (e.g. for
Japanese-language summaries).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .collector import SnapshotRow

JST = ZoneInfo("Asia/Tokyo")
DISCORD_COLOR_DEFAULT = 0x3fb950  # green-ish for DeFi


def _label(row: SnapshotRow, aliases: dict[str, str], max_chars: int = 40) -> str:
    if row.slug and row.slug in aliases:
        return aliases[row.slug]
    q = row.question or "(unknown)"
    return q if len(q) <= max_chars else q[: max_chars - 1].rstrip() + "…"


def _fmt_value(v: float | None) -> str:
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


def _fmt_delta_pct(d: float | None) -> str:
    if d is None:
        return "—"
    pct = d * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


# ---------- Discord ----------

def build_discord_embed(
    *,
    snapshot_date: datetime,
    gainers: list[SnapshotRow],
    losers: list[SnapshotRow],
    chains: list[SnapshotRow],
    aliases: dict[str, str],
    color: int = DISCORD_COLOR_DEFAULT,
    footer_text: str = "Auto-generated 3×/day · Data via DefiLlama public API",
) -> dict[str, Any]:
    date_str = snapshot_date.astimezone(JST).strftime("%Y-%m-%d")
    fields: list[dict[str, Any]] = []

    def _block(name: str, rows: list[SnapshotRow], show_delta: bool = True) -> dict[str, Any] | None:
        if not rows:
            return None
        lines = []
        for r in rows:
            value = _fmt_value(r.yes_price)
            if show_delta:
                delta = _fmt_delta_pct(r.one_day_change)
                lines.append(f"• {_label(r, aliases)}  **{value}**  {delta}")
            else:
                lines.append(f"• {_label(r, aliases)}  **{value}**")
        return {"name": name, "value": "\n".join(lines), "inline": False}

    for block in (
        _block("🚀 Top gainers (24h)", gainers),
        _block("📉 Top losers (24h)", losers),
        _block("🌐 Top chains (TVL)", chains, show_delta=False),
    ):
        if block is not None:
            fields.append(block)

    return {
        "title": "📊 DeFi Daily Snapshot",
        "description": f"**{date_str} (JST)**",
        "color": color,
        "fields": fields,
        "footer": {"text": footer_text},
        "timestamp": snapshot_date.astimezone(JST).isoformat(),
    }


# ---------- X (Twitter) ----------

X_MAX_CHARS = 280


def build_tweet(
    *,
    snapshot_date: datetime,
    gainers: list[SnapshotRow],
    losers: list[SnapshotRow],
    aliases: dict[str, str],
    hashtags: str = "#DeFi #Crypto #TVL",
) -> str:
    """Compress the snapshot into a single 280-char tweet.

    Strategy: header + top gainer + top loser + hashtags. If too long,
    progressively shorten labels then drop the loser.
    """
    date_str = snapshot_date.astimezone(JST).strftime("%m/%d JST")
    header = f"📊 DeFi Daily {date_str}"

    def render(g: list[SnapshotRow], l: list[SnapshotRow], label_max: int) -> str:
        lines = [header]
        if g:
            lines.append("🚀 " + " / ".join(
                f"{_label(r, aliases, max_chars=label_max)} {_fmt_delta_pct(r.one_day_change)}"
                for r in g
            ))
        if l:
            lines.append("📉 " + " / ".join(
                f"{_label(r, aliases, max_chars=label_max)} {_fmt_delta_pct(r.one_day_change)}"
                for r in l
            ))
        if hashtags:
            lines.append(hashtags)
        return "\n".join(lines)

    for label_max in (32, 24, 20, 16, 12):
        text = render(gainers[:3], losers[:3], label_max)
        if len(text) <= X_MAX_CHARS:
            return text

    # Drop bottom rows progressively.
    for n in (2, 1):
        for label_max in (24, 20, 16, 12):
            text = render(gainers[:n], losers[:n], label_max)
            if len(text) <= X_MAX_CHARS:
                return text

    return render(gainers[:1], [], 12)[:X_MAX_CHARS]
