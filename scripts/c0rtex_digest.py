#!/usr/bin/env python3
"""
c0rtex digest — cybersecurity news briefing.
fetches rss feeds, ranks articles by relevance, summarizes the top batch,
and queues the rest for on-demand delivery via the matrix bridge.

architecture:
    - pulls from configured rss feeds
    - deduplicates against previously seen articles (~/.c0rtex/digest_seen.json)
    - ranks articles by relevance to user's interests using ollama
    - summarizes the top batch (default 5) and sends to matrix
    - saves remaining articles to ~/.c0rtex/digest_queue.json
    - the matrix bridge handles "more" requests from the queue

usage:
    python c0rtex_digest.py

recommended cron (twice daily, 8am and 6pm):
    0 8,18 * * * /usr/bin/python3 /path/to/c0rtex_digest.py
"""

import json
import random
import hashlib
import re
import time
import requests
import feedparser
from datetime import datetime, timedelta
from c0rtex_log import get_logger
from c0rtex_paths import (
    CORTEX_DIR, DIGEST_SEEN_FILE, DIGEST_QUEUE_FILE, DIGESTS_DIR,
    OLLAMA_HOST, MATRIX_HOMESERVER, MATRIX_ACCESS_TOKEN, MATRIX_ROOM_ID,
)

log = get_logger("digest")

# ── config ──────────────────────────────────────────────────────────────────
MODEL = "qwen3.5:27b"

SEEN_FILE = DIGEST_SEEN_FILE
QUEUE_FILE = DIGEST_QUEUE_FILE
DIGEST_DIR = DIGESTS_DIR

# how many articles to send in the initial digest
BATCH_SIZE = 5
# max articles to process per run
MAX_ARTICLES = 20
# max age of articles to consider (in days)
MAX_AGE_DAYS = 2
# max characters of article content to send to the model
MAX_CONTENT_LENGTH = 3000

# ── rss feeds ───────────────────────────────────────────────────────────────

FEEDS = [
    # breaking security news
    ("BleepingComputer", "https://www.bleepingcomputer.com/feed/"),
    ("The Hacker News", "https://feeds.feedburner.com/TheHackersNews"),
    ("Krebs on Security", "https://krebsonsecurity.com/feed/"),

    # software
    ("The Register", "https://www.theregister.com/software/headlines.atom"),

    # vulnerability research
    ("PortSwigger Research", "https://portswigger.net/research/rss"),

    # other
    ("Hackaday", "https://hackaday.com/blog/feed"),
    ("Polygon", "https://www.polygon.com/feed/"),
    ("Low Tech Magazine", "https://solar.lowtechmagazine.com/posts/index.xml"),
]

# ── digest messages ─────────────────────────────────────────────────────────

DIGEST_START_MESSAGES = [
    "checking the feeds...",
    "time to see what the internet broke today.",
    "scanning the usual sources.",
    "pulling the latest from the security world.",
    "let me see what happened while you were gone.",
    "feed check starting. back in a few.",
    "reading the news so you don't have to.",
    "tapping into the feeds. one sec.",
    "alright, let's see who got breached today.",
    "firing up the rss parser. stand by.",
]

DIGEST_EMPTY_MESSAGES = [
    "nothing new since last check. the internet is suspiciously quiet.",
    "feeds are dry. either nothing happened or everything is on fire and no one's reported it yet.",
    "no new articles. enjoy the silence.",
    "checked everything. nothing worth your time right now.",
    "all quiet on the cyber front. for now.",
]

# ── matrix messaging ────────────────────────────────────────────────────────

def send_matrix_message(message: str):
    url = f"{MATRIX_HOMESERVER}/_matrix/client/v3/rooms/{MATRIX_ROOM_ID}/send/m.room.message"
    headers = {
        "Authorization": f"Bearer {MATRIX_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"msgtype": "m.text", "body": message}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"failed to send matrix message: {e}")


# ── seen articles tracking ──────────────────────────────────────────────────

def load_seen() -> dict:
    if SEEN_FILE.exists():
        try:
            return json.loads(SEEN_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_seen(seen: dict):
    cutoff = (datetime.now() - timedelta(days=30)).isoformat()
    pruned = {k: v for k, v in seen.items() if v.get("date", "") > cutoff}
    CORTEX_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(pruned, indent=2))


def article_hash(title: str, link: str) -> str:
    return hashlib.sha256(f"{title}:{link}".encode()).hexdigest()[:16]


# ── queue management ────────────────────────────────────────────────────────

def save_queue(articles: list):
    """save remaining articles to queue for the bridge to serve."""
    CORTEX_DIR.mkdir(parents=True, exist_ok=True)
    QUEUE_FILE.write_text(json.dumps(articles, indent=2))


def load_queue() -> list:
    """load queued articles."""
    if QUEUE_FILE.exists():
        try:
            return json.loads(QUEUE_FILE.read_text())
        except json.JSONDecodeError:
            return []
    return []


def clear_queue():
    """clear the queue."""
    if QUEUE_FILE.exists():
        QUEUE_FILE.write_text("[]")


# ── feed fetching ───────────────────────────────────────────────────────────

def fetch_feeds() -> list:
    articles = []
    cutoff = datetime.now() - timedelta(days=MAX_AGE_DAYS)

    for feed_name, feed_url in FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:10]:
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    published = datetime(*entry.updated_parsed[:6])

                if published and published < cutoff:
                    continue

                content = ""
                if hasattr(entry, "summary"):
                    content = entry.summary
                if hasattr(entry, "content") and entry.content:
                    content = entry.content[0].get("value", content)

                content = re.sub(r"<[^>]+>", " ", content)
                content = re.sub(r"\s+", " ", content).strip()

                articles.append({
                    "source": feed_name,
                    "title": entry.get("title", "untitled"),
                    "link": entry.get("link", ""),
                    "content": content[:MAX_CONTENT_LENGTH],
                    "published": published.isoformat() if published else datetime.now().isoformat(),
                })
        except Exception as e:
            print(f"error fetching {feed_name}: {e}")

    return articles


# ── ollama calls ────────────────────────────────────────────────────────────

def rank_articles(articles: list) -> list:
    """
    use ollama to rank articles by relevance.
    returns article indices in order of relevance.
    """
    titles = "\n".join(f"{i}. [{a['source']}] {a['title']}" for i, a in enumerate(articles))

    prompt = f"""you are ranking cybersecurity news articles by relevance.
rank articles that cover practical vulnerabilities, exploits, incident response,
reverse engineering, and hands-on security work higher than general news or policy.

here are today's articles:
{titles}

rank these by relevance. return ONLY a comma-separated list of the article numbers in order from most relevant to least relevant. no explanation, just the numbers.

example output: 3,7,1,4,0,2,5,6"""

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {"num_ctx": 4096}
    }

    log.ollama_request(MODEL, payload["messages"])
    t0 = time.time()
    try:
        resp = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "")
        log.ollama_response(MODEL, content, int((time.time() - t0) * 1000))

        # parse the ranked indices
        indices = []
        for part in content.strip().split(","):
            part = part.strip()
            if part.isdigit():
                idx = int(part)
                if 0 <= idx < len(articles) and idx not in indices:
                    indices.append(idx)

        # add any missing indices at the end (in case the model missed some)
        for i in range(len(articles)):
            if i not in indices:
                indices.append(i)

        return [articles[i] for i in indices]

    except Exception as e:
        log.error("rank_articles", str(e))
        print(f"ranking failed, using original order: {e}")
        return articles


def summarize_article(article: dict) -> str:
    prompt = f"""summarize this cybersecurity news article in 2-3 sentences. be specific about what happened, who was affected, and why it matters. write in lowercase, casual style. no markdown formatting.

source: {article['source']}
title: {article['title']}
content: {article['content']}

summary:"""

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {"num_ctx": 4096}
    }

    log.ollama_request(MODEL, payload["messages"])
    t0 = time.time()
    try:
        resp = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "failed to summarize.")
        log.ollama_response(MODEL, content, int((time.time() - t0) * 1000))
        return content
    except Exception as e:
        log.error("summarize_article", str(e))
        return f"summarization failed: {e}"


# ── digest composition ──────────────────────────────────────────────────────

def compose_digest(summaries: list, remaining: int) -> str:
    now = datetime.now().strftime("%A, %B %d at %I:%M %p")
    hour = datetime.now().hour

    if hour < 12:
        greeting = "morning digest"
    elif hour < 18:
        greeting = "afternoon digest"
    else:
        greeting = "evening digest"

    lines = [f"— c0rtex {greeting} | {now} —", ""]

    for item in summaries:
        lines.append(f"[{item['source']}] {item['title']}")
        lines.append(item["summary"])
        lines.append(item["link"])
        lines.append("")

    if remaining > 0:
        lines.append(f"— showing top {len(summaries)}. {remaining} more queued. say \"more\" for the next batch. —")
    else:
        lines.append(f"— {len(summaries)} article(s). that's everything. —")

    return "\n".join(lines)


# ── main ────────────────────────────────────────────────────────────────────

def main():
    log.session_start()
    now = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
    print(f"[{now}] c0rtex digest starting")

    CORTEX_DIR.mkdir(parents=True, exist_ok=True)
    DIGEST_DIR.mkdir(parents=True, exist_ok=True)

    # notify start
    send_matrix_message(random.choice(DIGEST_START_MESSAGES))

    # load seen articles
    seen = load_seen()

    # fetch feeds
    articles = fetch_feeds()
    print(f"fetched {len(articles)} articles from {len(FEEDS)} feeds")
    log.event("feeds_fetched", count=len(articles), feed_count=len(FEEDS))

    # filter out already-seen articles
    new_articles = []
    for article in articles:
        h = article_hash(article["title"], article["link"])
        if h not in seen:
            new_articles.append(article)
            seen[h] = {"date": article["published"], "title": article["title"]}

    print(f"{len(new_articles)} new articles to process")
    log.event("dedup_result", new=len(new_articles), skipped=len(articles) - len(new_articles))

    if not new_articles:
        send_matrix_message(random.choice(DIGEST_EMPTY_MESSAGES))
        print("no new articles. skipping digest.")
        save_seen(seen)
        clear_queue()
        return

    # cap at MAX_ARTICLES
    new_articles = new_articles[:MAX_ARTICLES]

    # rank articles by relevance
    print("ranking articles by relevance...")
    ranked = rank_articles(new_articles)

    # split into first batch and queue
    first_batch = ranked[:BATCH_SIZE]
    remaining = ranked[BATCH_SIZE:]

    # summarize the first batch
    summaries = []
    for i, article in enumerate(first_batch):
        print(f"summarizing [{i+1}/{len(first_batch)}]: {article['title'][:60]}...")
        summary = summarize_article(article)
        summaries.append({
            "source": article["source"],
            "title": article["title"],
            "link": article["link"],
            "summary": summary,
        })

    # save remaining articles to queue for "more" requests
    save_queue(remaining)
    print(f"queued {len(remaining)} articles for later")

    # compose and send digest
    digest = compose_digest(summaries, len(remaining))

    # save digest to file
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    digest_file = DIGEST_DIR / f"{timestamp}.md"
    digest_file.write_text(digest)
    print(f"digest saved to {digest_file}")

    # send to matrix
    send_matrix_message(digest)
    print("digest sent to matrix")

    # save seen articles
    save_seen(seen)
    print("done.")
    log.session_end()


if __name__ == "__main__":
    main()
