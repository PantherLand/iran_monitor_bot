# Iran News Monitor Bot

A Python script that monitors Iran-related news:

- Fetches Iran-related English news from NewsAPI on a schedule
- Uses the OpenRouter API to translate titles and summaries into Simplified Chinese
- Pushes updates to a target chat through a Telegram Bot
- Supports a `/summary` Telegram command to generate a same-day news summary
- Uses local `sent_news.json` deduplication to avoid duplicate sends

## Features

- Checks for news every 10 minutes by default
- Default query: `Iran OR Tehran OR IRGC`
- Fetches the latest 10 English articles by default
- Sends a startup notification before the first check
- Polls Telegram for `/summary` commands and replies with a Chinese daily digest

## Requirements

- Python 3.9+

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

1. Copy the example config:

```bash
cp .env.example .env
```

2. Fill in `.env` with your real values:

```env
TELEGRAM_BOT_TOKEN=your Telegram Bot Token
TELEGRAM_CHAT_ID=your Telegram Chat ID
OPENROUTER_API_KEY=your OpenRouter API Key
NEWS_API_KEY=your NewsAPI Key
CHECK_INTERVAL_MINUTES=10
NEWS_QUERY=Iran OR Tehran OR IRGC
NEWS_PAGE_SIZE=10
OPENROUTER_MODEL=
```

Leave `OPENROUTER_MODEL` empty to use your OpenRouter account default model, or set it to a specific OpenRouter model ID.

## Run

```bash
python3 iran_monitor_bot.py
```

After startup, the script keeps running and polls on the interval set by `CHECK_INTERVAL_MINUTES`.

## Railway Deployment

This project supports two Railway deployment styles:

1. Railway Cron Job (recommended)
2. Long-running worker service

### Option 1: Railway Cron Job

This is the better fit for Railway because the process runs once, sends any new items, and exits.

Set this environment variable in Railway:

```env
RUN_ONCE=true
```

Use this start command:

```bash
python3 iran_monitor_bot.py
```

Then create a Railway Cron schedule and trigger the service on your preferred interval.

Note: in Cron mode, `/summary` commands are only processed when the next scheduled run starts.

### Option 2: Long-Running Worker

If you want to keep the current in-process scheduler, do not set `RUN_ONCE`.

Use this start command:

```bash
python3 iran_monitor_bot.py
```

In this mode, the script stays online and checks every `CHECK_INTERVAL_MINUTES`.

### Recommended Railway Variables

Set these in Railway service variables:

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
OPENROUTER_API_KEY=...
NEWS_API_KEY=...
CHECK_INTERVAL_MINUTES=10
NEWS_QUERY=Iran OR Tehran OR IRGC
NEWS_PAGE_SIZE=10
OPENROUTER_MODEL=openai/gpt-4o-mini
RUN_ONCE=true
```

## Main Dependencies

- `requests`: calls NewsAPI, OpenRouter API, and Telegram Bot API
- `schedule`: handles periodic job scheduling
- `python-dotenv`: loads local configuration from `.env`

## Generated File

- `sent_news.json`: auto-generated hash cache of already-sent news items
- `bot_state.json`: stores the last handled Telegram update ID to avoid reprocessing commands

## Notes

- `.env` contains sensitive API keys and should not be committed
- If Telegram formatting looks broken, it is usually caused by special characters in upstream content; the script now applies basic HTML escaping
- NewsAPI free plans are rate-limited, so avoid setting the polling interval too low

## Possible Improvements

- Add more filtering keywords
- Add source or region filters
- Add retries and persistent logging
- Run it as a long-lived service with systemd, pm2, or Docker
