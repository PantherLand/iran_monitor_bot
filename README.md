# Iran News Monitor Bot

A Python script that monitors Iran-related news:

- Fetches Iran-related English news from NewsAPI on a schedule
- Uses the OpenRouter API to translate titles and summaries into Simplified Chinese
- Pushes updates to a target chat through a Telegram Bot
- Uses local `sent_news.json` deduplication to avoid duplicate sends

## Features

- Checks for news every 10 minutes by default
- Default query: `Iran OR Tehran OR IRGC`
- Fetches the latest 10 English articles by default
- Sends a startup notification before the first check

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

## Main Dependencies

- `requests`: calls NewsAPI, OpenRouter API, and Telegram Bot API
- `schedule`: handles periodic job scheduling
- `python-dotenv`: loads local configuration from `.env`

## Generated File

- `sent_news.json`: auto-generated hash cache of already-sent news items

## Notes

- `.env` contains sensitive API keys and should not be committed
- If Telegram formatting looks broken, it is usually caused by special characters in upstream content; the script now applies basic HTML escaping
- NewsAPI free plans are rate-limited, so avoid setting the polling interval too low

## Possible Improvements

- Add more filtering keywords
- Add source or region filters
- Add retries and persistent logging
- Run it as a long-lived service with systemd, pm2, or Docker
