"""Daily snapshot data collection for DeFi (DefiLlama).

Two REST calls per run:
  - /protocols    → universe of protocols, used for gainers + losers
  - /v2/chains    → universe of chains,    used for the chains section

Each row is shaped like the original ``SnapshotRow`` so the renderer,
formatter, jp_translator and DB persistence are unchanged. We reinterpret
two fields:
    yes_price       → TVL in USD (large numbers, e.g. 24_500_000_000)
    one_day_change  → 24h % change as fraction (0.052 == +5.2%)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from ..defillama_client import DefiLlamaClient

log = logging.getLogger(__name__)


# Protocol categories we want to drop. CEX listings, fundraising trackers,
# and bridge/treasury aggregators are noisy or off-topic for a "DeFi daily".
EXCLUDED_PROTOCOL_CATEGORIES = {
    "CEX",
    "Chain",                # entire-chain rollups duplicate /v2/chains
    "Treasury",
    "Token",
    "Yield Aggregator",     # noisy 24h swings; consider re-enabling later
    "Foundation",
    "Insurance",            # tiny TVL universe
}

# Chain names to drop (ghost chains, deprecated, or aliasing duplicates).
EXCLUDED_CHAINS = {
    "Hyperliquid",          # listed but mostly synthetic perp TVL
    "ICP",
    "Mixin",
}


@dataclass
class SnapshotRow:
    market_id: str
    slug: str | None
    question: str
    yes_price: float | None         # repurposed: TVL in USD
    one_day_change: float | None    # repurposed: 24h % change as fraction
    volume_24h_usd: float           # always 0.0 — kept for schema compat
    tag_slugs: list[str]
    category: str | None            # "Protocol" | "Chain"
    event_slug: str | None = None
    event_title: str | None = None


# ---------------------------------------------------------------------------
# Collectors
# ---------------------------------------------------------------------------
def collect_protocols(
    client: DefiLlamaClient,
    *,
    min_tvl_usd: float = 100_000_000,
    excluded_categories: Iterable[str] = EXCLUDED_PROTOCOL_CATEGORIES,
    max_abs_change_pct: float = 80.0,
) -> list[SnapshotRow]:
    """Return protocols with non-trivial TVL and a sane 24h change.

    Filtering:
    - TVL ≥ ``min_tvl_usd`` ($100M default) — drops the long tail of <$10M
      protocols where 24h change is dominated by oracle noise.
    - Drop categories in ``excluded_categories``.
    - Drop change_1d magnitudes > ``max_abs_change_pct`` — these are almost
      always reporting glitches (delisting, integration changes), not real moves.
    """
    excluded = {c.strip() for c in excluded_categories}
    raw = client.protocols()
    rows: list[SnapshotRow] = []
    for p in raw:
        tvl = float(p.get("tvl") or 0.0)
        if tvl < min_tvl_usd:
            continue
        cat = p.get("category") or ""
        if cat in excluded:
            continue
        change_pct = p.get("change_1d_pct")
        if change_pct is None or abs(change_pct) > max_abs_change_pct:
            change_frac: float | None = None
        else:
            change_frac = change_pct / 100.0

        slug = p.get("slug") or p.get("name", "").lower().replace(" ", "-")
        rows.append(
            SnapshotRow(
                market_id=f"protocol:{slug}",
                slug=slug,
                question=f"{p.get('name', slug)} - {cat or 'DeFi'}",
                yes_price=tvl,
                one_day_change=change_frac,
                volume_24h_usd=0.0,
                tag_slugs=[cat.lower()] if cat else [],
                category="Protocol",
            )
        )

    log.info("protocols: %d rows after filters (from %d raw)", len(rows), len(raw))
    return rows


def collect_chains(
    client: DefiLlamaClient,
    *,
    min_tvl_usd: float = 50_000_000,
    excluded_chains: Iterable[str] = EXCLUDED_CHAINS,
) -> list[SnapshotRow]:
    """Return chains by current TVL. No 24h change available from /v2/chains."""
    excluded = {c.strip() for c in excluded_chains}
    raw = client.chains()
    rows: list[SnapshotRow] = []
    for c in raw:
        tvl = float(c.get("tvl") or 0.0)
        if tvl < min_tvl_usd:
            continue
        name = c.get("name", "")
        if name in excluded:
            continue
        slug = name.lower().replace(" ", "-")
        rows.append(
            SnapshotRow(
                market_id=f"chain:{slug}",
                slug=slug,
                question=f"{name} - L1/L2",
                yes_price=tvl,
                one_day_change=None,
                volume_24h_usd=0.0,
                tag_slugs=["chain"],
                category="Chain",
            )
        )

    log.info("chains: %d rows after filters (from %d raw)", len(rows), len(raw))
    return rows


# ---------------------------------------------------------------------------
# Selectors (per section)
# ---------------------------------------------------------------------------
def top_gainers(rows: list[SnapshotRow], *, n: int = 3) -> list[SnapshotRow]:
    eligible = [
        r for r in rows
        if r.category == "Protocol"
        and r.one_day_change is not None
        and r.one_day_change > 0
    ]
    eligible.sort(key=lambda r: r.one_day_change or 0.0, reverse=True)
    return eligible[:n]


def top_losers(rows: list[SnapshotRow], *, n: int = 3) -> list[SnapshotRow]:
    eligible = [
        r for r in rows
        if r.category == "Protocol"
        and r.one_day_change is not None
        and r.one_day_change < 0
    ]
    eligible.sort(key=lambda r: r.one_day_change or 0.0)
    return eligible[:n]


def top_chains(rows: list[SnapshotRow], *, n: int = 3) -> list[SnapshotRow]:
    chains = [r for r in rows if r.category == "Chain"]
    chains.sort(key=lambda r: r.yes_price or 0.0, reverse=True)
    return chains[:n]
