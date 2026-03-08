# War Reports Monitor Bot

A Python bot that tracks mainstream-media war reports and sends a Chinese summary to Telegram every 4 hours.

## What It Does

- Pulls recent war-related reports from NewsAPI (`everything` endpoint)
- Filters to mainstream media domains
- Summarizes the past 4-hour window with OpenRouter
- Sends one digest message to Telegram
- Supports manual `/summary` command in Telegram

## Default Behavior

- Execute every 4 hours
- Each run summarizes the last 4 hours
- Query keywords focus on war/conflict/military events
- Preview cards are disabled in Telegram messages
- Pull interval (`SUMMARY_INTERVAL_HOURS`) and lookback window (`LOOKBACK_HOURS`) are independent

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

1. Copy env template:

```bash
cp .env.example .env
```

2. Fill `.env`:

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
OPENROUTER_API_KEY=...
NEWS_API_KEY=...

SUMMARY_INTERVAL_HOURS=4
LOOKBACK_HOURS=4
NEWS_QUERY=war OR warfare OR military OR missile OR drone OR strike OR conflict OR ceasefire
MAINSTREAM_MEDIA_DOMAINS=reuters.com,apnews.com,bbc.com,nytimes.com,washingtonpost.com,theguardian.com,wsj.com,bloomberg.com,ft.com,aljazeera.com,cnn.com
NEWS_PAGE_SIZE=30
OPENROUTER_MODEL=
RUN_ONCE=
```

## Run

```bash
python3 iran_monitor_bot.py
```

When running as a long-lived process:

- Bot starts immediately and sends one startup summary
- Then it sends scheduled summaries every `SUMMARY_INTERVAL_HOURS`
- Sending `/summary` in the configured chat triggers an on-demand summary

## Railway / Cron Mode

For cron-style deployment, set:

```env
RUN_ONCE=true
```

In `RUN_ONCE=true`, each run:

- handles pending Telegram commands once
- generates one summary
- exits

If you want exact every-4-hour execution in cron mode, schedule the job at a 4-hour interval.
Even if cron is misconfigured (for example every 2 hours), the bot still fetches reports from `now - LOOKBACK_HOURS` (default 4).

## Generated State File

- `bot_state.json`: stores last handled Telegram `update_id` to avoid command reprocessing
