"""
Phase 8 — Publisher.

Code only — no model. Posts approved generated assets to platform APIs.

Hard constraints:
  - Never posts to Reddit. Reddit promotional automation violates Reddit's rules.
    Humans post manually after reviewing the Planner's plan.
  - Never posts to LinkedIn. Automated posting violates LinkedIn's user agreement.
  - Only processes assets where GeneratedAsset is provided and ReviewResult.approved is True.
  - Rate limits are enforced per-platform.
  - Writes an audit row for every attempt (success or failure) via store.log_publish().

To extend: add a new branch in _route() and a matching adapter function.
Do not add Reddit or LinkedIn branches.
"""

from __future__ import annotations

import time
import os
import logging
from typing import Callable

from roxi.content.models import GeneratedAsset, PublishResult, ReviewResult

log = logging.getLogger(__name__)

_FORBIDDEN_PLATFORMS = frozenset({"reddit", "linkedin"})

_RATE_LIMIT_SECONDS: dict[str, float] = {
    "twitter": 1.0,
    "x": 1.0,
    "instagram": 2.0,
    "facebook": 1.0,
    "tiktok": 2.0,
    "blog": 0.5,
    "email": 0.0,
}

_last_send: dict[str, float] = {}


def publish(
    asset: GeneratedAsset,
    review: ReviewResult,
    platform: str,
) -> PublishResult:
    """
    Publish an approved asset to a platform.

    Returns a PublishResult regardless of success so callers can log it.
    Raises ValueError for forbidden platforms (Reddit, LinkedIn) or unapproved reviews.
    """
    platform_key = platform.lower().strip()

    if platform_key in _FORBIDDEN_PLATFORMS:
        raise ValueError(
            f"Automated posting to {platform} is not permitted. "
            "Reddit violates Reddit's rules; LinkedIn violates their user agreement. "
            "A human must post manually."
        )

    if not review.approved:
        return PublishResult(
            item_id=asset.item_id,
            platform=platform,
            success=False,
            error="ReviewResult.approved is False — cannot publish.",
        )

    _enforce_rate_limit(platform_key)

    adapter = _route(platform_key)
    if adapter is None:
        return PublishResult(
            item_id=asset.item_id,
            platform=platform,
            success=False,
            error=f"No publisher adapter registered for platform '{platform}'.",
        )

    try:
        result = adapter(asset, platform)
        _last_send[platform_key] = time.time()
        _log_publish(asset.item_id, platform, result)
        return result
    except Exception as exc:
        log.exception("publish failed: item=%s platform=%s", asset.item_id, platform)
        result = PublishResult(
            item_id=asset.item_id,
            platform=platform,
            success=False,
            error=str(exc),
        )
        _log_publish(asset.item_id, platform, result)
        return result


def _enforce_rate_limit(platform_key: str) -> None:
    gap = _RATE_LIMIT_SECONDS.get(platform_key, 1.0)
    last = _last_send.get(platform_key, 0.0)
    wait = gap - (time.time() - last)
    if wait > 0:
        time.sleep(wait)


def _route(platform_key: str) -> Callable[[GeneratedAsset, str], PublishResult] | None:
    if platform_key in ("twitter", "x"):
        return _post_twitter
    if platform_key == "instagram":
        return _post_instagram
    if platform_key in ("facebook", "fb"):
        return _post_facebook
    if platform_key == "blog":
        return _post_blog
    return None


def _post_twitter(asset: GeneratedAsset, platform: str) -> PublishResult:
    import requests

    bearer = os.environ.get("TWITTER_BEARER_TOKEN")
    api_key = os.environ.get("TWITTER_API_KEY")
    api_secret = os.environ.get("TWITTER_API_SECRET")
    access_token = os.environ.get("TWITTER_ACCESS_TOKEN")
    access_secret = os.environ.get("TWITTER_ACCESS_SECRET")

    if not all([api_key, api_secret, access_token, access_secret]):
        raise EnvironmentError(
            "TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, "
            "TWITTER_ACCESS_SECRET required for Twitter publishing."
        )

    from requests_oauthlib import OAuth1

    auth = OAuth1(api_key, api_secret, access_token, access_secret)
    text = asset.text_content or ""
    if len(text) > 280:
        text = text[:277] + "…"

    r = requests.post(
        "https://api.twitter.com/2/tweets",
        auth=auth,
        json={"text": text},
        timeout=15,
    )
    r.raise_for_status()
    tweet_id = r.json().get("data", {}).get("id", "")
    return PublishResult(
        item_id=asset.item_id,
        platform=platform,
        success=True,
        post_url=f"https://twitter.com/i/web/status/{tweet_id}",
    )


def _post_instagram(asset: GeneratedAsset, platform: str) -> PublishResult:
    import requests

    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
    ig_user_id = os.environ.get("INSTAGRAM_USER_ID")
    if not token or not ig_user_id:
        raise EnvironmentError(
            "INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_USER_ID required."
        )

    if asset.media_type == "text" or not asset.url:
        raise ValueError("Instagram requires an image or video URL.")

    r = requests.post(
        f"https://graph.facebook.com/v18.0/{ig_user_id}/media",
        params={
            "image_url": asset.url,
            "caption": asset.text_content or "",
            "access_token": token,
        },
        timeout=30,
    )
    r.raise_for_status()
    container_id = r.json().get("id")

    r2 = requests.post(
        f"https://graph.facebook.com/v18.0/{ig_user_id}/media_publish",
        params={"creation_id": container_id, "access_token": token},
        timeout=30,
    )
    r2.raise_for_status()
    media_id = r2.json().get("id", "")
    return PublishResult(
        item_id=asset.item_id,
        platform=platform,
        success=True,
        post_url=f"https://www.instagram.com/p/{media_id}/",
    )


def _post_facebook(asset: GeneratedAsset, platform: str) -> PublishResult:
    import requests

    token = os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN")
    page_id = os.environ.get("FACEBOOK_PAGE_ID")
    if not token or not page_id:
        raise EnvironmentError(
            "FACEBOOK_PAGE_ACCESS_TOKEN and FACEBOOK_PAGE_ID required."
        )

    # Token passed in Authorization header, not query params, to keep it out of server logs.
    headers = {"Authorization": f"Bearer {token}"}
    if asset.media_type == "text":
        payload = {"message": asset.text_content or ""}
        endpoint = f"https://graph.facebook.com/v18.0/{page_id}/feed"
    else:
        payload = {"url": asset.url or "", "caption": asset.text_content or ""}
        endpoint = f"https://graph.facebook.com/v18.0/{page_id}/photos"

    r = requests.post(endpoint, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    post_id = r.json().get("id", "")
    return PublishResult(
        item_id=asset.item_id,
        platform=platform,
        success=True,
        post_url=f"https://www.facebook.com/{post_id}",
    )


def _post_blog(asset: GeneratedAsset, platform: str) -> PublishResult:
    """
    Blog publish stub. Point BLOG_WEBHOOK_URL at your CMS (Ghost, WordPress, etc.)
    and set BLOG_WEBHOOK_SECRET.
    """
    import requests

    webhook_url = os.environ.get("BLOG_WEBHOOK_URL")
    secret = os.environ.get("BLOG_WEBHOOK_SECRET", "")
    if not webhook_url:
        raise EnvironmentError("BLOG_WEBHOOK_URL required for blog publishing.")

    r = requests.post(
        webhook_url,
        json={
            "item_id": asset.item_id,
            "content": asset.text_content,
            "image_url": asset.url,
        },
        headers={"X-Webhook-Secret": secret},
        timeout=30,
    )
    r.raise_for_status()
    post_url = r.json().get("url")
    return PublishResult(
        item_id=asset.item_id,
        platform=platform,
        success=True,
        post_url=post_url,
    )


def _log_publish(item_id: str, platform: str, result: PublishResult) -> None:
    try:
        from roxi import store
        store.log_publish(item_id=item_id, platform=platform, result=result)
    except Exception:
        log.warning("Could not write publish audit row for item %s", item_id)
