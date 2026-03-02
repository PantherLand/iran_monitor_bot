#!/usr/bin/env python3
"""
Iran Monitor -> Claude翻译 -> Telegram Bot 推送
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

# ==================== 配置区域（必填）====================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "").strip()

# ==================== 配置区域（可选）====================

CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "10"))
NEWS_QUERY = os.getenv("NEWS_QUERY", "Iran OR Tehran OR IRGC").strip()
NEWS_PAGE_SIZE = int(os.getenv("NEWS_PAGE_SIZE", "10"))
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514").strip()

# ======================================================

SENT_NEWS_FILE = "sent_news.json"


def validate_config():
    required = {
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
        "NEWS_API_KEY": NEWS_API_KEY,
    }
    return [name for name, value in required.items() if not value]

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
        print(f"[ERROR] 获取新闻: {e}")
        return []

def translate(text):
    if not text:
        return ""
    try:
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY,
                     "anthropic-version": "2023-06-01",
                     "Content-Type": "application/json"},
            json={"model": ANTHROPIC_MODEL, "max_tokens": 500,
                  "messages": [{"role": "user", "content":
                      f"将以下英文翻译成中文，直接输出翻译，不加解释：\n\n{text}"}]},
            timeout=30)
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()
    except Exception as e:
        print(f"[ERROR] 翻译: {e}")
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
        print(f"[ERROR] TG发送: {e}")
        return False

def check_and_push():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 检查新闻...")
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
            "🔴 <b>伊朗实时动态</b>", "",
            f"📌 <b>{safe_title}</b>",
        ]
        if safe_desc:
            msg_parts += ["", f"📝 {safe_desc}"]
        msg_parts += ["", f"🕐 {pub}", f"📰 {safe_source}"]
        if a.get("url"):
            msg_parts.append(f"🔗 <a href='{html.escape(a['url'], quote=True)}'>原文</a>")

        if send_tg("\n".join(msg_parts)):
            sent.add(h)
            new_count += 1
            time.sleep(2)

    save_sent_news(sent)
    print(f"  → 推送 {new_count} 条新消息")

def main():
    print("伊朗新闻监控 Bot 启动")
    missing = validate_config()
    if missing:
        print("❌ 缺少必要配置，请检查 .env：")
        for key in missing:
            print(f"   - {key}")
        return

    send_tg(f"🚀 <b>伊朗新闻监控已启动</b>\n每 {CHECK_INTERVAL_MINUTES} 分钟检查一次\n翻译：Claude AI")
    check_and_push()
    schedule.every(CHECK_INTERVAL_MINUTES).minutes.do(check_and_push)

    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    main()
