# 🎬 Streaming Watchlist — Live Content Update Engine

A continuously refreshed watchlist of content available on **legitimate streaming services in India**:
Netflix India · Prime Video India · JioHotstar · SonyLIV · ZEE5 · Apple TV+ · JioCinema · YouTube.

**Initialized:** 28 Aug 2026, ~23:45 IST (first baseline scan)

## How it stays fresh

| Layer | Schedule (Asia/Kolkata) | What it does |
|---|---|---|
| **Hourly check** | Every hour at :07 | Light delta scan. Detects new titles, new episodes/seasons, removals, platform moves, trending shifts. **Only processes detected changes — never rebuilds the database.** |
| **Daily deep refresh** | Every day at 09:00 | Full pass per platform: add/remove/availability/episodes/trending → score recalculation → re-evaluate MUST WATCH, Hidden Gems, Indian Picks, YouTube Picks → link verification → writes today's report. |

Both run as isolated scheduled jobs (manageable in the AutoClaw 「定时」 panel). All results are written to the files below.

## Files

| File | Purpose |
|---|---|
| [data/catalog.json](data/catalog.json) | The catalog: all tracked titles, sections, provisional scores, last-checked stamps |
| [data/change-log.md](data/change-log.md) | **Rolling 24-hour log** — `DATE \| TIME \| TITLE \| CHANGE \| PLATFORM \| ACTION`; entries older than 24h are auto-archived at build time |
| [data/change-log-archive.md](data/change-log-archive.md) | Deprecated change-log entries (older than 24h), preserved for audit |
| [state/last-check.json](state/last-check.json) | Per-platform last-checked timestamps |
| [reports/2026-08-28.md](reports/2026-08-28.md) | Daily "Today's Streaming Update" reports (one per day) |
| [reports/latest-alerts.md](reports/latest-alerts.md) | Standing alerts: 🔥 DON'T MISS / ⏰ WATCH BEFORE IT LEAVES / 🔄 PLATFORM CHANGE |
| [web/index.html](web/index.html) | **Web dashboard** — self-contained page built from the data files; regenerated automatically after every job run |
| [web/build.py](web/build.py) | Dashboard generator: `python3 streaming-watchlist/web/build.py` — also fetches poster art (TMDB). Posters activate once a free TMDB API key is saved to `web/tmdb_key.txt`; until then cards show styled placeholders. Per-title override: add `"poster": "<image-url>"` to an entry in `catalog.json`. |

## Commands (type any of these in chat)

| Command | Effect |
|---|---|
| `REFRESH` | Immediate availability/content refresh right now |
| `HOURLY UPDATE` | Run the hourly delta check now |
| `DAILY UPDATE` | Run the full daily refresh now |
| `WHAT'S NEW` | Show recently added content |
| `WHAT LEFT` | Show recently removed content |
| `LEAVING SOON` | Important titles that may leave soon |
| `PLATFORM CHANGES` | Titles that moved between services |
| `TODAY'S PICKS` | Today's best recommendations |
| `LAST UPDATE` | When each platform was last checked |

## Scoring model (0–100, recalculated daily)

`QUALITY (25) + CURRENT AVAILABILITY (15) + CRITICAL RESPONSE (15) + AUDIENCE RESPONSE (10) + PERSONAL PREFERENCE (15) + RECENCY (10) + WATCH VALUE (10)`

- A new mediocre title stays **below** an older exceptional one. Never auto-promoted for being new.
- Personal-preference profile starts minimal and sharpens from your feedback (thumbs up/down on picks).
- Each entry carries a `scoreConfidence` until enough signal exists.

## Data freshness & link policy

- Every recommendation carries **Last checked: date/time IST**.
- Stale/unverified data is flagged: `⚠️ Availability needs verification` — never presented as live.
- Links prefer **official platform/title pages**; fallback is the platform's **official search/discovery page**.
- **Never** piracy or illegal streaming sources. Aggregators (JustWatch/FlixPatrol/RT) are used as *detection sources only*, never as watch links.

## Tracked platforms

Netflix India · Prime Video India · JioHotstar · SonyLIV · ZEE5 · Apple TV+ · JioCinema · YouTube (docs/channels + trending)
