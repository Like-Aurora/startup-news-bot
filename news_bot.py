"""
スタートアップ系ニュースをRSSから集めて、Discord Webhookに投稿するスクリプト。

使い方:
  DISCORD_WEBHOOK_URL=... python news_bot.py
  python news_bot.py --dry-run      # 投稿せず内容だけ表示
"""

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

import feedparser

# ───── 設定 ─────────────────────────────────────────
# 追加・削除は自由。RSS/Atom のURLなら何でもOK。
FEEDS = [
    # 日本
    {"name": "THE BRIDGE", "url": "https://thebridge.jp/feed", "color": 0x2E86DE},
    {"name": "国内 資金調達ニュース (Google News)",
     "url": "https://news.google.com/rss/search?q=%E3%82%B9%E3%82%BF%E3%83%BC%E3%83%88%E3%82%A2%E3%83%83%E3%83%97+%E8%B3%87%E9%87%91%E8%AA%BF%E9%81%94+when:1d&hl=ja&gl=JP&ceid=JP:ja",
     "color": 0xE67E22},
    # 海外
    {"name": "TechCrunch Startups", "url": "https://techcrunch.com/category/startups/feed/", "color": 0x0A9E01},
    {"name": "Crunchbase News", "url": "https://news.crunchbase.com/feed/", "color": 0x146AFF},
]

HOURS_BACK = 24          # 何時間前までの記事を拾うか
MAX_PER_FEED = 6         # 1ソースあたりの最大件数
JST = timezone(timedelta(hours=9))
# ────────────────────────────────────────────────────


def entry_time(entry):
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(time.mktime(t), tz=timezone.utc)
    return None


def collect(feed, since):
    parsed = feedparser.parse(feed["url"], agent="startup-news-bot/1.0")
    items = []
    for e in parsed.entries:
        t = entry_time(e)
        if t is None or t < since:
            continue
        title = (e.get("title") or "").strip().replace("[", "［").replace("]", "］")
        link = e.get("link")
        if title and link:
            items.append((t, title, link))
    items.sort(reverse=True)
    return items[:MAX_PER_FEED]


def build_embeds(results):
    embeds = []
    for feed, items in results:
        lines = [f"• [{title[:150]}]({link})" for _, title, link in items]
        desc = "\n".join(lines)[:4000]
        embeds.append({"title": feed["name"], "description": desc, "color": feed["color"]})
    return embeds


def chunk_embeds(embeds):
    """Discordの制限（1メッセージ10embed・合計6000字）に収まるよう分割"""
    batch, size = [], 0
    for em in embeds:
        n = len(em["title"]) + len(em["description"])
        if batch and (len(batch) == 10 or size + n > 5800):
            yield batch
            batch, size = [], 0
        batch.append(em)
        size += n
    if batch:
        yield batch


def post(webhook, payload):
    req = urllib.request.Request(
        webhook,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "startup-news-bot/1.0"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()
    time.sleep(1)  # レート制限よけ


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    since = datetime.now(timezone.utc) - timedelta(hours=HOURS_BACK)
    results = []
    for feed in FEEDS:
        try:
            items = collect(feed, since)
        except Exception as ex:  # 1ソースが落ちても他は続行
            print(f"[warn] {feed['name']}: {ex}", file=sys.stderr)
            continue
        if items:
            results.append((feed, items))

    today = datetime.now(JST).strftime("%Y/%m/%d")
    header = f"🚀 **スタートアップニュース {today}**"
    if not results:
        header += "\n過去24時間の新着はありませんでした。"

    batches = list(chunk_embeds(build_embeds(results))) or [[]]
    payloads = [{"content": header if i == 0 else None, "embeds": b} for i, b in enumerate(batches)]

    if args.dry_run:
        print(json.dumps(payloads, ensure_ascii=False, indent=2))
        return

    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        sys.exit("DISCORD_WEBHOOK_URL が設定されていません")
    for p in payloads:
        post(webhook, {k: v for k, v in p.items() if v is not None})
    print(f"posted {sum(len(i) for _, i in results)} items")


if __name__ == "__main__":
    main()
