"""
スタートアップ系ニュースをRSSから集めて、Discord Webhookに投稿するスクリプト。
日本と海外から、それぞれ新しい記事を指定件数（count）選んで送る。

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
REGIONS = [
    {
        "title": "🇯🇵 日本",
        "count": 3,              # 送る件数
        "color": 0xE74C3C,
        "feeds": [
            "https://thebridge.jp/feed",
            "https://news.google.com/rss/search?q=%E3%82%B9%E3%82%BF%E3%83%BC%E3%83%88%E3%82%A2%E3%83%83%E3%83%97+%E8%B3%87%E9%87%91%E8%AA%BF%E9%81%94+when:1d&hl=ja&gl=JP&ceid=JP:ja",
        ],
    },
    {
        "title": "🌏 海外",
        "count": 1,              # 送る件数
        "color": 0x2E86DE,
        "feeds": [
            "https://techcrunch.com/category/startups/feed/",
            "https://news.crunchbase.com/feed/",
        ],
    },
]

HOURS_BACK = 24          # 何時間前までの記事を候補にするか
JST = timezone(timedelta(hours=9))
# ────────────────────────────────────────────────────


def entry_time(entry):
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(time.mktime(t), tz=timezone.utc)
    return None


def collect(url, since):
    parsed = feedparser.parse(url, agent="startup-news-bot/1.0")
    source = parsed.feed.get("title", "")
    items = []
    for e in parsed.entries:
        t = entry_time(e)
        if t is None or t < since:
            continue
        title = (e.get("title") or "").strip().replace("[", "［").replace("]", "］")
        link = e.get("link")
        if title and link:
            items.append({"time": t, "title": title, "link": link, "source": source})
    items.sort(key=lambda x: x["time"], reverse=True)
    return items


def pick(region, since):
    """各ソースの新しい順に交互に取り、重複を除いて count 件選ぶ"""
    per_feed = []
    for url in region["feeds"]:
        try:
            per_feed.append(collect(url, since))
        except Exception as ex:  # 1ソースが落ちても他は続行
            print(f"[warn] {url}: {ex}", file=sys.stderr)

    chosen, seen = [], set()
    i = 0
    while len(chosen) < region["count"] and any(i < len(f) for f in per_feed):
        for f in per_feed:
            if i < len(f) and len(chosen) < region["count"]:
                key = f[i]["title"][:40]
                if key not in seen:
                    seen.add(key)
                    chosen.append(f[i])
        i += 1
    return chosen


def build_embed(region, items):
    if items:
        lines = [f"• [{it['title'][:150]}]({it['link']})" for it in items]
        desc = "\n".join(lines)
    else:
        desc = "過去24時間の新着はありませんでした。"
    return {"title": region["title"], "description": desc, "color": region["color"]}


def post(webhook, payload):
    req = urllib.request.Request(
        webhook,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "startup-news-bot/1.0"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    since = datetime.now(timezone.utc) - timedelta(hours=HOURS_BACK)
    embeds = [build_embed(r, pick(r, since)) for r in REGIONS]
    today = datetime.now(JST).strftime("%Y/%m/%d")
    payload = {"content": f"🚀 **スタートアップニュース {today}**", "embeds": embeds}

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        sys.exit("DISCORD_WEBHOOK_URL が設定されていません")
    post(webhook, payload)
    print("posted")


if __name__ == "__main__":
    main()
