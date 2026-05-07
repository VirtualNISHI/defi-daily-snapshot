"""DefiLlama public-API client.

No API key, no auth, generous rate limits. We pull two endpoints:

  GET  /protocols          → every tracked protocol with TVL + change_1d
  GET  /v2/chains          → every tracked chain with current TVL

The collector consumes both and turns them into ``SnapshotRow``-shaped
records so the rest of the daily-snapshot pipeline (renderer, formatter,
jp_translator, persist) is unchanged.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

log = logging.getLogger(__name__)

BASE = "https://api.llama.fi"


class DefiLlamaError(RuntimeError):
    pass


def _to_float(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


class DefiLlamaClient:
    def __init__(
        self,
        *,
        user_agent: str = "defi-daily-snapshot/0.1",
        timeout: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=BASE,
            timeout=timeout,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "DefiLlamaClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _get(self, path: str) -> Any:
        r = self._client.get(path)
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------
    def protocols(self) -> list[dict[str, Any]]:
        """Every tracked protocol. Each item has, at minimum:
            name, slug, tvl, change_1d (percent, NOT fraction),
            change_7d, category, chains, mcap, ...
        """
        data = self._get("/protocols")
        if not isinstance(data, list):
            raise DefiLlamaError(f"unexpected /protocols payload: {type(data).__name__}")
        out: list[dict[str, Any]] = []
        for p in data:
            try:
                out.append({
                    "name": str(p.get("name") or "").strip(),
                    "slug": str(p.get("slug") or "").strip(),
                    "tvl": _to_float(p.get("tvl")),
                    "change_1d_pct": _to_float(p.get("change_1d")),
                    "change_7d_pct": _to_float(p.get("change_7d")),
                    "category": str(p.get("category") or "").strip(),
                    "chains": list(p.get("chains") or []),
                    "url": str(p.get("url") or "").strip(),
                })
            except Exception as exc:  # one bad row shouldn't kill the run
                log.debug("skipping malformed protocol row: %s", exc)
        return out

    def chains(self) -> list[dict[str, Any]]:
        """Every tracked chain with current TVL.

        DefiLlama's `/v2/chains` returns the present-day snapshot only — no
        24h change column. The collector treats chains as a separate bucket
        ranked purely by current TVL.
        """
        data = self._get("/v2/chains")
        if not isinstance(data, list):
            raise DefiLlamaError(f"unexpected /v2/chains payload: {type(data).__name__}")
        out: list[dict[str, Any]] = []
        for c in data:
            try:
                out.append({
                    "name": str(c.get("name") or "").strip(),
                    "tvl": _to_float(c.get("tvl")),
                    "token_symbol": str(c.get("tokenSymbol") or "").strip(),
                    "gecko_id": str(c.get("gecko_id") or "").strip(),
                })
            except Exception as exc:
                log.debug("skipping malformed chain row: %s", exc)
        return out
