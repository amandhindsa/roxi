from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from roxi.config import VerticalConfig
from roxi.models import RawItem

log = logging.getLogger(__name__)

# Phase 1 collector — job boards via Playwright
# A fresh browser is launched per fetch() call; _fetch_detail uses a second page
# so the search results page is never navigated away from.


def _get_browser():
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True)
    return browser, p


def fetch(vertical: VerticalConfig) -> list[RawItem]:
    if not vertical.channels.job_boards.enabled:
        return []

    items: list[RawItem] = []
    browser, playwright = _get_browser()
    try:
        ua = "Mozilla/5.0 (compatible; Roxi/0.1; +https://roxi.ai/bot)"
        search_page = browser.new_page(user_agent=ua)
        detail_page = browser.new_page(user_agent=ua)
        for query in vertical.channels.job_boards.queries:
            before = len(items)
            items.extend(_search_indeed(search_page, detail_page, query))
            count = len(items) - before
            if count == 0:
                log.warning(
                    "job_boards: query %r returned 0 results — "
                    "Indeed may have changed its layout or blocked the request",
                    query,
                )
            else:
                log.info("job_boards: query %r → %d items", query, count)
            time.sleep(3)
    finally:
        browser.close()
        playwright.stop()

    return items


def _search_indeed(search_page, detail_page, query: str) -> list[RawItem]:
    url = f"https://ca.indeed.com/jobs?q={query.replace(' ', '+')}&l=Canada"
    try:
        search_page.goto(url, wait_until="domcontentloaded", timeout=15000)
    except Exception as exc:
        log.warning("job_boards: failed to load search page for %r: %s", query, exc)
        return []

    # Collect all card metadata first — before any navigation that would stale the handles.
    card_data: list[tuple[str, str, str]] = []
    cards = search_page.query_selector_all("div.job_seen_beacon")[:20]
    for card in cards:
        try:
            title_el = card.query_selector("h2.jobTitle")
            company_el = card.query_selector("[data-testid='company-name']")
            link_el = card.query_selector("h2.jobTitle a")
            if not title_el or not link_el:
                continue
            title = title_el.inner_text().strip()
            company = company_el.inner_text().strip() if company_el else ""
            href = link_el.get_attribute("href") or ""
            source_url = f"https://ca.indeed.com{href}" if href.startswith("/") else href
            card_data.append((title, company, source_url))
        except Exception as exc:
            log.debug("job_boards: skipping card for %r: %s", query, exc)
            continue

    # Now fetch detail pages on the separate page object — search results stay intact.
    items = []
    for title, company, source_url in card_data:
        try:
            detail_text = _fetch_detail(detail_page, source_url)
            body = f"Company: {company}\n\n{detail_text}" if company else detail_text
            items.append(RawItem(
                channel="job_boards",
                source_url=source_url,
                fetched_at=datetime.now(tz=timezone.utc),
                title=title,
                body=body[:8000],
            ))
            time.sleep(2)
        except Exception as exc:
            log.warning("job_boards: failed to fetch detail for %r (%s): %s", title, source_url, exc)
            continue

    return items


def _fetch_detail(page, url: str) -> str:
    if not url or not url.startswith("http"):
        return ""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        desc_el = page.query_selector("#jobDescriptionText")
        return desc_el.inner_text().strip() if desc_el else ""
    except Exception:
        return ""
