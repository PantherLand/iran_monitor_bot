#!/usr/bin/env python3
"""
Iran Monitor -> OpenRouter Translation -> Telegram Bot Push
"""

import hashlib
import html
import json
import os
import time
from datetime import datetime, timedelta, timezone

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
RUN_ONCE = os.getenv("RUN_ONCE", "").strip().lower() in {"1", "true", "yes", "on"}

# ======================================================

SENT_NEWS_FILE = "sent_news.json"
BOT_STATE_FILE = "bot_state.json"
UTC_PLUS_8 = timezone(timedelta(hours=8))


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


def print_runtime_env_status():
    checks = {
        "TELEGRAM_BOT_TOKEN": bool(TELEGRAM_BOT_TOKEN),
        "TELEGRAM_CHAT_ID": bool(TELEGRAM_CHAT_ID),
        "OPENROUTER_API_KEY": bool(OPENROUTER_API_KEY),
        "NEWS_API_KEY": bool(NEWS_API_KEY),
        "RUN_ONCE": RUN_ONCE,
    }
    print("Runtime env status:")
    for key, present in checks.items():
        print(f"  - {key}: {'set' if present else 'missing'}")

def load_sent_news():
    if os.path.exists(SENT_NEWS_FILE):
        with open(SENT_NEWS_FILE) as f:
            return set(json.load(f))
    return set()

def save_sent_news(s):
    with open(SENT_NEWS_FILE, "w") as f:
        json.dump(list(s)[-500:], f)

def load_bot_state():
    if os.path.exists(BOT_STATE_FILE):
        with open(BOT_STATE_FILE) as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    return {"last_update_id": 0}

def save_bot_state(state):
    with open(BOT_STATE_FILE, "w") as f:
        json.dump(state, f)

def get_iran_news(page_size=None):
    try:
        r = requests.get("https://newsapi.org/v2/everything", params={
            "q": NEWS_QUERY,
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": page_size or NEWS_PAGE_SIZE,
            "apiKey": NEWS_API_KEY,
        }, timeout=15)
        r.raise_for_status()
        return r.json().get("articles", [])
    except Exception as e:
        print(f"[ERROR] Failed to fetch news: {e}")
        return []

def call_openrouter(prompt, max_tokens=500):
    try:
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "max_tokens": max_tokens,
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
        print(f"[ERROR] OpenRouter request failed: {e}")
        return None

def translate(text):
    if not text:
        return ""
    return call_openrouter(
        "Translate the following English text into Simplified Chinese. "
        "Return only the translation with no extra explanation.\n\n"
        f"{text}",
        max_tokens=500,
    )

def parse_published_at(article):
    published_at = article.get("publishedAt", "")
    if not published_at:
        return None
    try:
        return (
            datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            .astimezone(UTC_PLUS_8)
        )
    except Exception:
        return None

def send_daily_summary():
    print("  -> Building daily summary...")
    today = datetime.now(UTC_PLUS_8).date()
    articles = []
    for article in get_iran_news(page_size=max(20, NEWS_PAGE_SIZE)):
        title = (article.get("title") or "").strip()
        if not title or title == "[Removed]":
            continue
        published_at = parse_published_at(article)
        if published_at and published_at.date() != today:
            continue
        articles.append(article)
        if len(articles) >= 8:
            break

    if not articles:
        return send_tg(
            "📰 <b>今日新闻摘要</b>\n\n"
            "今天还没有抓取到符合条件的新闻。"
        )

    prompt_lines = [
        "You are a news analyst.",
        "Based on the Iran-related articles below, write a concise daily summary in Simplified Chinese for Telegram.",
        "Requirements:",
        "1. Start with one short overview sentence.",
        "2. Then provide 3-5 short bullet points using '-' as the bullet marker.",
        "3. Only use facts supported by the provided articles.",
        "4. If multiple articles cover the same topic, merge them.",
        "5. Do not include markdown or HTML.",
        "",
        f"Date (UTC+8): {today.isoformat()}",
        "",
        "Articles:",
    ]

    for idx, article in enumerate(articles, start=1):
        published_at = parse_published_at(article)
        published_text = (
            published_at.strftime("%Y-%m-%d %H:%M UTC+8")
            if published_at else article.get("publishedAt", "")
        )
        prompt_lines.append(f"{idx}. Title: {article.get('title', '')}")
        prompt_lines.append(f"   Description: {article.get('description', '') or ''}")
        prompt_lines.append(f"   Source: {article.get('source', {}).get('name', '')}")
        prompt_lines.append(f"   Published: {published_text}")

    summary = call_openrouter("\n".join(prompt_lines), max_tokens=700)
    if not summary:
        return send_tg(
            "📰 <b>今日新闻摘要</b>\n\n"
            "摘要生成失败，请稍后重试。"
        )

    return send_tg(
        "📰 <b>今日新闻摘要</b>\n\n"
        f"{html.escape(summary)}"
    )

def get_telegram_updates(offset, timeout=0):
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
            params={
                "offset": offset,
                "timeout": timeout,
                "allowed_updates": json.dumps(["message"]),
            },
            timeout=timeout + 5 if timeout else 15,
        )
        r.raise_for_status()
        payload = r.json()
        if not payload.get("ok"):
            return []
        return payload.get("result", [])
    except Exception as e:
        print(f"[ERROR] Telegram getUpdates failed: {e}")
        return []

def handle_telegram_commands(timeout=0):
    state = load_bot_state()
    updates = get_telegram_updates(state.get("last_update_id", 0), timeout=timeout)
    if not updates:
        return

    last_update_id = state.get("last_update_id", 0)
    for update in updates:
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            last_update_id = max(last_update_id, update_id + 1)

        message = update.get("message") or {}
        chat_id = str((message.get("chat") or {}).get("id", "")).strip()
        text = (message.get("text") or "").strip()
        if not text or not chat_id or chat_id != TELEGRAM_CHAT_ID:
            continue

        command = text.split()[0].split("@", 1)[0].lower()
        if command == "/summary":
            print("  -> Received /summary command")
            send_tg("🧾 正在生成今日重要新闻摘要，请稍候...")
            send_daily_summary()

    state["last_update_id"] = last_update_id
    save_bot_state(state)

def send_tg(msg):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg,
                  "parse_mode": "HTML", "disable_web_page_preview": True},
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
            pub = (
                datetime.fromisoformat(a["publishedAt"].replace("Z", "+00:00"))
                .astimezone(UTC_PLUS_8)
                .strftime("%Y-%m-%d %H:%M UTC+8")
            )
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
    print_runtime_env_status()
    missing = validate_config()
    if missing:
        print("Missing required configuration. Check your .env file:")
        for key in missing:
            print(f"   - {key}")
        return
    if not validate_openrouter_key():
        return
    if RUN_ONCE:
        handle_telegram_commands(timeout=0)
        check_and_push()
        return

    send_tg(
        f"🚀 <b>Iran News Monitor is online</b>\n"
        f"Checking every {CHECK_INTERVAL_MINUTES} minute(s)\n"
        f"Translation: OpenRouter"
    )
    handle_telegram_commands(timeout=0)
    check_and_push()
    schedule.every(CHECK_INTERVAL_MINUTES).minutes.do(check_and_push)

    while True:
        handle_telegram_commands(timeout=5)
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()
