#!/usr/bin/env python3
"""
War Reports Monitor -> OpenRouter Summary -> Telegram Push
"""

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

SUMMARY_INTERVAL_HOURS = int(os.getenv("SUMMARY_INTERVAL_HOURS", "4"))
LOOKBACK_HOURS = int(os.getenv("LOOKBACK_HOURS", "4"))
NEWSAPI_RETRY_DEFAULT_SECONDS = int(os.getenv("NEWSAPI_RETRY_DEFAULT_SECONDS", "1800"))
NEWS_QUERY = os.getenv(
    "NEWS_QUERY",
    "war OR warfare OR military OR missile OR drone OR strike OR conflict OR ceasefire",
).strip()
NEWS_PAGE_SIZE = int(os.getenv("NEWS_PAGE_SIZE", "30"))
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "").strip()
RUN_ONCE = os.getenv("RUN_ONCE", "").strip().lower() in {"1", "true", "yes", "on"}

DEFAULT_MAINSTREAM_MEDIA_DOMAINS = (
    "reuters.com,apnews.com,bbc.com,nytimes.com,washingtonpost.com,"
    "theguardian.com,wsj.com,bloomberg.com,ft.com,aljazeera.com,cnn.com"
)
MAINSTREAM_MEDIA_DOMAINS = [
    x.strip()
    for x in os.getenv("MAINSTREAM_MEDIA_DOMAINS", DEFAULT_MAINSTREAM_MEDIA_DOMAINS).split(",")
    if x.strip()
]

# ======================================================

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
        "SUMMARY_INTERVAL_HOURS": SUMMARY_INTERVAL_HOURS,
        "LOOKBACK_HOURS": LOOKBACK_HOURS,
        "MAINSTREAM_MEDIA_DOMAINS": ",".join(MAINSTREAM_MEDIA_DOMAINS),
        "RUN_ONCE": RUN_ONCE,
    }
    print("Runtime env status:")
    for key, present in checks.items():
        print(f"  - {key}: {'set' if present else 'missing'}")


def load_bot_state():
    if os.path.exists(BOT_STATE_FILE):
        with open(BOT_STATE_FILE) as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    return {"last_update_id": 0, "newsapi_retry_not_before": 0}


def save_bot_state(state):
    with open(BOT_STATE_FILE, "w") as f:
        json.dump(state, f)


def call_openrouter(prompt, max_tokens=900):
    try:
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
        if OPENROUTER_MODEL:
            payload["model"] = OPENROUTER_MODEL

        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "X-Title": "War Reports Monitor Bot",
            },
            json=payload,
            timeout=45,
        )
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


def send_tg(msg):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": msg,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"[ERROR] Telegram send failed: {e}")
        return False


def parse_published_at(article):
    published_at = article.get("publishedAt", "")
    if not published_at:
        return None
    try:
        return datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except Exception:
        return None


def fetch_recent_war_reports(hours):
    now_utc = datetime.now(timezone.utc)
    since_utc = now_utc - timedelta(hours=hours)
    params = {
        "q": NEWS_QUERY,
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": NEWS_PAGE_SIZE,
        "from": since_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "apiKey": NEWS_API_KEY,
    }
    if MAINSTREAM_MEDIA_DOMAINS:
        params["domains"] = ",".join(MAINSTREAM_MEDIA_DOMAINS)

    try:
        r = requests.get("https://newsapi.org/v2/everything", params=params, timeout=20)
        r.raise_for_status()
        raw_articles = r.json().get("articles", [])
    except requests.HTTPError as e:
        response = e.response
        status = response.status_code if response is not None else None
        retry_after_seconds = None
        if response is not None:
            retry_after = (response.headers.get("Retry-After") or "").strip()
            if retry_after.isdigit():
                retry_after_seconds = int(retry_after)
        print(f"[ERROR] Failed to fetch war reports: {e}")
        return [], since_utc, now_utc, {
            "status": status,
            "retry_after_seconds": retry_after_seconds,
            "message": str(e),
        }
    except Exception as e:
        print(f"[ERROR] Failed to fetch war reports: {e}")
        return [], since_utc, now_utc, {
            "status": None,
            "retry_after_seconds": None,
            "message": str(e),
        }

    seen = set()
    results = []
    for article in raw_articles:
        title = (article.get("title") or "").strip()
        url = (article.get("url") or "").strip()
        if not title or title == "[Removed]":
            continue
        key = url or title
        if key in seen:
            continue
        published = parse_published_at(article)
        if published and published < since_utc:
            continue
        seen.add(key)
        results.append(article)

    return results, since_utc, now_utc, None


def build_summary_prompt(articles, since_utc, now_utc):
    lines = [
        "You are a geopolitical news analyst.",
        "Create a concise but information-dense summary in Simplified Chinese based only on the reports below.",
        "Requirements:",
        "1. First line: one-sentence overview.",
        "2. Then 4-7 bullet points with concrete details (actors, locations, actions, impacts, timeline).",
        "3. If there are conflicting claims, explicitly mark uncertainty.",
        "4. Keep names/transliterations accurate and do not invent facts.",
        "5. No markdown tables. No HTML.",
        "",
        f"Time window UTC: {since_utc.strftime('%Y-%m-%d %H:%M')} -> {now_utc.strftime('%Y-%m-%d %H:%M')}",
        "",
        "Reports:",
    ]

    for idx, article in enumerate(articles[:25], start=1):
        published = parse_published_at(article)
        published_text = (
            published.astimezone(UTC_PLUS_8).strftime("%Y-%m-%d %H:%M UTC+8")
            if published
            else article.get("publishedAt", "")
        )
        lines.append(f"{idx}. Title: {article.get('title', '')}")
        lines.append(f"   Description: {article.get('description', '') or ''}")
        lines.append(f"   Source: {article.get('source', {}).get('name', '')}")
        lines.append(f"   Published: {published_text}")

    return "\n".join(lines)


def send_interval_summary(trigger="schedule"):
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Building {LOOKBACK_HOURS}h summary ({trigger})...")
    state = load_bot_state()
    now_ts = int(time.time())
    retry_not_before_ts = int(state.get("newsapi_retry_not_before", 0) or 0)
    if retry_not_before_ts > now_ts:
        retry_local = datetime.fromtimestamp(retry_not_before_ts, tz=timezone.utc).astimezone(UTC_PLUS_8)
        print(
            "[WARN] Skipping NewsAPI request due to active cooldown "
            f"until {retry_local.strftime('%Y-%m-%d %H:%M:%S UTC+8')}"
        )
        return send_tg(
            "⚠️ <b>News source rate-limited</b>\n\n"
            f"Next retry after: {retry_local.strftime('%m-%d %H:%M:%S')} UTC+8"
        )

    articles, since_utc, now_utc, fetch_error = fetch_recent_war_reports(LOOKBACK_HOURS)
    since_local = since_utc.astimezone(UTC_PLUS_8)
    now_local = now_utc.astimezone(UTC_PLUS_8)

    if fetch_error:
        if fetch_error.get("status") == 429:
            retry_after_seconds = fetch_error.get("retry_after_seconds") or NEWSAPI_RETRY_DEFAULT_SECONDS
            retry_not_before = int(time.time()) + retry_after_seconds
            state["newsapi_retry_not_before"] = retry_not_before
            save_bot_state(state)
            retry_local = datetime.fromtimestamp(retry_not_before, tz=timezone.utc).astimezone(UTC_PLUS_8)
            print(
                "[WARN] NewsAPI rate-limited. "
                f"Cooling down for {retry_after_seconds}s until {retry_local.strftime('%Y-%m-%d %H:%M:%S UTC+8')}"
            )
            return send_tg(
                "⚠️ <b>NewsAPI quota/rate limit reached</b>\n\n"
                f"Next retry after: {retry_local.strftime('%m-%d %H:%M:%S')} UTC+8"
            )
        return send_tg(
            "⚠️ <b>Failed to fetch reports</b>\n\n"
            "News source request failed. Will retry in the next cycle."
        )

    if state.get("newsapi_retry_not_before"):
        state["newsapi_retry_not_before"] = 0
        save_bot_state(state)

    if not articles:
        return send_tg(
            f"🛰 <b>{LOOKBACK_HOURS}小时战争摘要</b>\n\n"
            f"🕐 时间范围: {since_local.strftime('%m-%d %H:%M')} - {now_local.strftime('%m-%d %H:%M')} UTC+8\n"
            "未抓取到主流媒体的相关战争报道。"
        )

    prompt = build_summary_prompt(articles, since_utc, now_utc)
    summary = call_openrouter(prompt, max_tokens=1000)
    if not summary:
        return send_tg(
            f"🛰 <b>{LOOKBACK_HOURS}小时战争摘要</b>\n\n"
            "摘要生成失败，请稍后重试。"
        )

    sources = sorted({
        (a.get("source", {}) or {}).get("name", "").strip()
        for a in articles
        if (a.get("source", {}) or {}).get("name", "").strip()
    })
    msg_parts = [
        f"🛰 <b>{LOOKBACK_HOURS}小时战争摘要</b>",
        "",
        f"🕐 时间范围: {since_local.strftime('%m-%d %H:%M')} - {now_local.strftime('%m-%d %H:%M')} UTC+8",
        f"📰 报道数: {len(articles)} | 媒体数: {len(sources)}",
        "",
        html.escape(summary),
    ]

    links = []
    for article in articles[:5]:
        url = (article.get("url") or "").strip()
        title = (article.get("title") or "").strip()
        source = (article.get("source", {}) or {}).get("name", "").strip() or "Unknown"
        if not url or not title:
            continue
        safe_title = html.escape(title[:80])
        safe_source = html.escape(source)
        safe_url = html.escape(url, quote=True)
        links.append(f"• <a href='{safe_url}'>{safe_source}: {safe_title}</a>")

    if links:
        msg_parts += ["", "🔗 参考报道:", *links]

    return send_tg("\n".join(msg_parts))


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
            send_tg(f"🧾 正在生成过去{LOOKBACK_HOURS}小时战争摘要，请稍候...")
            send_interval_summary(trigger="command")

    state["last_update_id"] = last_update_id
    save_bot_state(state)


def main():
    print("War Reports Monitor Bot started")
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
        send_interval_summary(trigger="run_once")
        return

    send_tg(
        "🚀 <b>战争报告监控已启动</b>\n"
        f"每 {SUMMARY_INTERVAL_HOURS} 小时汇总一次\n"
        f"每次覆盖过去 {LOOKBACK_HOURS} 小时\n"
        "来源: 主流媒体 (NewsAPI domains)"
    )
    handle_telegram_commands(timeout=0)
    send_interval_summary(trigger="startup")
    schedule.every(SUMMARY_INTERVAL_HOURS).hours.do(send_interval_summary, "schedule")

    while True:
        handle_telegram_commands(timeout=5)
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
