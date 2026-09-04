"""
Phase 3 collector — Reddit via official API (praw, script-type OAuth).

Required env vars: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from roxi.config import VerticalConfig
from roxi.models import RawItem

_SEARCH_TERMS = [
    "eManifest",
    "CBSA customs",
    "cross-border trucking software",
    "TMS dispatch Canada US",
    "customs paperwork carrier",
    "FMCSA authority Canada",
]


def fetch(vertical: VerticalConfig) -> list[RawItem]:
    if not vertical.channels.reddit.enabled:
        return []

    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    user_agent = os.environ.get("REDDIT_USER_AGENT", "roxi/0.1 by Hauler AI")

    if not client_id or not client_secret:
        raise EnvironmentError(
            "REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET must be set for Reddit collection"
        )

    import praw

    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    )

    items: list[RawItem] = []
    subreddits = [s.lstrip("r/") for s in vertical.channels.reddit.subreddits]

    for sub_name in subreddits:
        try:
            sub = reddit.subreddit(sub_name)
            items.extend(_fetch_subreddit(sub, vertical))
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Reddit subreddit %s failed: %s", sub_name, exc)

    for term in _SEARCH_TERMS:
        for sub_name in subreddits:
            try:
                sub = reddit.subreddit(sub_name)
                for post in sub.search(term, sort="new", time_filter="week", limit=25):
                    item = _post_to_raw(post, sub_name)
                    if item and item not in items:
                        items.append(item)
            except Exception:
                continue

    return _dedupe_urls(items)


def _fetch_subreddit(sub, vertical: VerticalConfig) -> list[RawItem]:
    items: list[RawItem] = []
    try:
        for post in sub.new(limit=100):
            item = _post_to_raw(post, sub.display_name)
            if item:
                items.append(item)
    except Exception:
        pass
    return items


def _post_to_raw(post, subreddit: str) -> RawItem | None:
    try:
        title = post.title or ""
        selftext = post.selftext or ""
        if not selftext.strip():
            return None

        author = str(post.author) if post.author else "unknown"
        body = f"Posted by u/{author}\n\n{selftext}"

        post.comments.replace_more(limit=0)
        top_comments = []
        for comment in list(post.comments)[:5]:
            if hasattr(comment, "body") and comment.body:
                top_comments.append(f"u/{comment.author}: {comment.body[:300]}")
        if top_comments:
            body += "\n\n--- Top comments ---\n" + "\n\n".join(top_comments)

        return RawItem(
            channel="reddit",
            source_url=f"https://reddit.com{post.permalink}",
            fetched_at=datetime.fromtimestamp(post.created_utc, tz=timezone.utc),
            title=title[:200],
            body=body[:6000],
        )
    except Exception:
        return None


def _dedupe_urls(items: list[RawItem]) -> list[RawItem]:
    seen: set[str] = set()
    out: list[RawItem] = []
    for item in items:
        if item.source_url not in seen:
            seen.add(item.source_url)
            out.append(item)
    return out
