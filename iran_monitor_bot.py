#!/usr/bin/env python3
"""
Iran Monitor -> OpenRouter Translation -> Telegram Bot Push
"""

import hashlib
import html
import json
import os
import time
from datetime import datetime

import requests
import schedule
from dotenv import load_dotenv

load_dotenv()

# ==================== Required Configuration ====================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "").strip()

# ==================== Optional Configuration ====================

CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "10"))
NEWS_QUERY = os.getenv("NEWS_QUERY", "Iran OR Tehran OR IRGC").strip()
NEWS_PAGE_SIZE = int(os.getenv("NEWS_PAGE_SIZE", "10"))
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "").strip()

# ======================================================

SENT_NEWS_FILE = "sent_news.json"


def validate_config():
    required = {
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
        "OPENROUTER_API_KEY": OPENROUTER_API_KEY,
        "NEWS_API_KEY": NEWS_API_KEY,
    }
    return [name for name, value in required.items() if not value]


def validate_openrouter_key():
    # OpenAI project keys start with sk-proj- and will not work with OpenRouter.
    if OPENROUTER_API_KEY.startswith("sk-proj-"):
        print("The configured OPENROUTER_API_KEY looks like an OpenAI key (sk-proj-...).")
        print("Use a real OpenRouter key from https://openrouter.ai/keys instead.")
        return False
    return True

def load_sent_news():
    if os.path.exists(SENT_NEWS_FILE):
        with open(SENT_NEWS_FILE) as f:
            return set(json.load(f))
    return set()

def save_sent_news(s):
    with open(SENT_NEWS_FILE, "w") as f:
        json.dump(list(s)[-500:], f)

def get_iran_news():
    try:
        r = requests.get("https://newsapi.org/v2/everything", params={
            "q": NEWS_QUERY,
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": NEWS_PAGE_SIZE,
            "apiKey": NEWS_API_KEY,
        }, timeout=15)
        r.raise_for_status()
        return r.json().get("articles", [])
    except Exception as e:
        print(f"[ERROR] Failed to fetch news: {e}")
        return []

def translate(text):
    if not text:
        return ""
    try:
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Translate the following English text into Simplified Chinese. "
                        "Return only the translation with no extra explanation.\n\n"
                        f"{text}"
                    ),
                }
            ],
            "max_tokens": 500,
        }
        if OPENROUTER_MODEL:
            payload["model"] = OPENROUTER_MODEL

        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "X-Title": "Iran News Monitor Bot",
            },
            json=payload,
            timeout=30)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_parts = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            ]
            return "".join(text_parts).strip()
        return None
    except Exception as e:
        print(f"[ERROR] Translation failed: {e}")
        return None

def send_tg(msg):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg,
                  "parse_mode": "HTML", "disable_web_page_preview": False},
            timeout=15)
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"[ERROR] Telegram send failed: {e}")
        return False

def check_and_push():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Checking news...")
    sent = load_sent_news()
    new_count = 0

    for a in get_iran_news():
        h = hashlib.md5((a.get("url") or a.get("title","")).encode()).hexdigest()
        if h in sent:
            continue

        title = a.get("title", "")
        if not title or title == "[Removed]":
            continue

        print(f"  → {title[:60]}...")
        t_title = translate(title)
        if not t_title:
            continue

        desc = a.get("description", "") or ""
        t_desc = translate(desc[:400]) if len(desc) > 20 else ""

        try:
            pub = datetime.fromisoformat(a["publishedAt"].replace("Z","+00:00")).strftime("%Y-%m-%d %H:%M UTC")
        except:
            pub = a.get("publishedAt", "")

        safe_title = html.escape(t_title)
        safe_desc = html.escape(t_desc) if t_desc else ""
        safe_source = html.escape(a.get("source", {}).get("name", ""))

        msg_parts = [
            "🔴 <b>Iran Live Update</b>", "",
            f"📌 <b>{safe_title}</b>",
        ]
        if safe_desc:
            msg_parts += ["", f"📝 {safe_desc}"]
        msg_parts += ["", f"🕐 Published: {pub}", f"📰 Source: {safe_source}"]
        if a.get("url"):
            msg_parts.append(f"🔗 <a href='{html.escape(a['url'], quote=True)}'>Original Link</a>")

        if send_tg("\n".join(msg_parts)):
            sent.add(h)
            new_count += 1
            time.sleep(2)

    save_sent_news(sent)
    print(f"  -> Sent {new_count} new message(s)")

def main():
    print("Iran News Monitor Bot started")
    missing = validate_config()
    if missing:
        print("Missing required configuration. Check your .env file:")
        for key in missing:
            print(f"   - {key}")
        return
    if not validate_openrouter_key():
        return

    send_tg(
        f"🚀 <b>Iran News Monitor is online</b>\n"
        f"Checking every {CHECK_INTERVAL_MINUTES} minute(s)\n"
        f"Translation: OpenRouter"
    )
    check_and_push()
    schedule.every(CHECK_INTERVAL_MINUTES).minutes.do(check_and_push)

    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    main()
