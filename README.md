# DeFi Daily Snapshot

A free, low-maintenance bot that posts a 1200×720 image card to **Discord and X** three times per day, summarising the DeFi market state from [DefiLlama](https://defillama.com)'s public API.

Three sections:

- 🚀 **Top gainers (24h)** — protocols with the largest positive 24h TVL change.
- 📉 **Top losers (24h)** — protocols with the largest negative 24h TVL change.
- 🌐 **Top chains (TVL)** — chains ranked by current TVL.

Adapted from the [polymarket-BOT](https://github.com/VirtualNISHI/polymarket-BOT) template, swapping the data layer for DefiLlama.

## Stack

| Component | What |
| --- | --- |
| **Data** | DefiLlama `/protocols` + `/v2/chains` (no API key, no rate-limit issues) |
| **Image** | Pillow + pilmoji + Noto CJK (1200×720 dark card) |
| **Translation** | Gemini 2.5 Flash (free tier) — translates protocol categories to JP |
| **Persistence** | SQLite, force-pushed to `bot-state` branch each run |
| **Schedule** | GitHub Actions cron, 3×/day at 00:05 / 08:05 / 16:05 JST |
| **Posting** | Discord webhook (image attachment) + X v2 tweet with v1.1 media upload |

## Setup

1. **Click "Use this template"** on GitHub or `git clone` and re-init.

2. **GitHub Secrets** — repo Settings → Secrets and variables → Actions:

   | Required | Optional |
   | --- | --- |
   | `DAILY_SNAPSHOT_DISCORD_WEBHOOK_URL` (or `DISCORD_WEBHOOK_URL`) | `GEMINI_API_KEY` (drops to English-only labels if missing) |
   | `X_API_KEY` | `ANTHROPIC_API_KEY` (alternative to Gemini) |
   | `X_API_SECRET` | |
   | `X_ACCESS_TOKEN` | |
   | `X_ACCESS_SECRET` | |

3. **Test the workflow** — Actions → `daily-snapshot` → Run workflow with `dry_run: true` to render and log without posting. Verify the rendered image, then run with `dry_run: false`.

4. **Schedule.** Default cadence is 00:05 / 08:05 / 16:05 JST (`5 15,23,7 * * *` UTC). Edit `.github/workflows/daily-snapshot.yml` to change.

## Local dry-run

```bash
pip install -e .
sudo apt-get install -y fonts-noto-cjk          # Linux only — Windows uses Yu Gothic
python scripts/run_daily.py --dry-run
```

The card is rendered, the prospective tweet text is logged, but nothing is posted.

## Tuning

Edit `config/settings.yaml`:

- `min_volume_24h_usd` (reinterpreted as min protocol TVL — default $100M)
- `enable_discord` / `enable_x` toggles
- `display_aliases` for manual per-slug Japanese labels
- `jp_translation_provider` (`gemini` or `anthropic`)

For a hard category exclusion list, edit `EXCLUDED_PROTOCOL_CATEGORIES` and `EXCLUDED_CHAINS` in `src/daily_snapshot/collector.py`.

## License

MIT (inherits from polymarket-BOT template).
