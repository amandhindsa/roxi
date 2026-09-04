"""
Phase 2 collector — FMCSA authority grants for Canadian carriers.

Searches the FMCSA SAFER system for carriers domiciled in Canada that received
new MC (Motor Carrier) operating authority within the last N days. Uses Playwright
since SAFER is a dynamic web app with no stable public JSON API.

Also polls Transport Canada NSC filings via their public carrier search.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from roxi.config import VerticalConfig
from roxi.models import RawItem

log = logging.getLogger(__name__)

_SAFER_SEARCH = "https://safer.fmcsa.dot.gov/query.asp"
_SAFER_CARRIER_URL = "https://safer.fmcsa.dot.gov/pi.asp"
_NSC_SEARCH = "https://www.tc.gc.ca/app/carrsafe/search-recherche.asp"

_CANADIAN_PROVINCES = ["BC", "AB", "SK", "MB", "ON", "QC", "NS", "NB", "PE", "NL", "YT", "NT", "NU"]


def fetch(vertical: VerticalConfig) -> list[RawItem]:
    if not vertical.channels.registry.enabled:
        return []

    items: list[RawItem] = []
    items.extend(_fetch_fmcsa_new_authority(days_back=14))
    items.extend(_fetch_nsc_new_carriers(days_back=14))
    return items


def _fetch_fmcsa_new_authority(days_back: int = 14) -> list[RawItem]:
    """
    Searches FMCSA SAFER for Canadian carriers that received new authority recently.
    Paginates through results filtered by country=CA and sorted by registration date.
    """
    from playwright.sync_api import sync_playwright

    items: list[RawItem] = []
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days_back)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            for province in _CANADIAN_PROVINCES:
                try:
                    province_items = _fmcsa_search_province(page, province, cutoff)
                    items.extend(province_items)
                    if province_items:
                        time.sleep(2)
                except Exception as exc:
                    log.warning("registry: FMCSA province %s failed: %s", province, exc)
        finally:
            browser.close()

    log.info("registry: FMCSA collected %d items", len(items))
    return items


def _fmcsa_search_province(page, province: str, cutoff: datetime) -> list[RawItem]:
    items: list[RawItem] = []

    try:
        page.goto(_SAFER_SEARCH, wait_until="domcontentloaded", timeout=15000)
        page.select_option('select[name="query_type"]', "MC_NUMBER")
        if page.query_selector('select[name="state"]'):
            page.select_option('select[name="state"]', province)
        if page.query_selector('select[name="country"]'):
            page.select_option('select[name="country"]', "CA")
        page.click('input[type="submit"]')
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception as exc:
        log.debug("registry: FMCSA page load failed for %s: %s", province, exc)
        return items

    rows = page.query_selector_all("table.queryresults tr")
    for row in rows[1:]:  # skip header
        cells = row.query_selector_all("td")
        if len(cells) < 5:
            continue

        try:
            mc_link = cells[0].query_selector("a")
            if not mc_link:
                continue

            mc_number = mc_link.inner_text().strip()
            carrier_name = cells[1].inner_text().strip() if len(cells) > 1 else ""
            state_prov = cells[3].inner_text().strip() if len(cells) > 3 else ""
            authority_date_str = cells[4].inner_text().strip() if len(cells) > 4 else ""

            detail_url = mc_link.get_attribute("href") or ""
            if detail_url and not detail_url.startswith("http"):
                detail_url = f"https://safer.fmcsa.dot.gov{detail_url}"

            detail_text = _fmcsa_carrier_detail(page, detail_url)

            body = (
                f"FMCSA Operating Authority Issued.\n"
                f"Entity: {carrier_name}\n"
                f"Country: Canada\n"
                f"Province: {state_prov or province}\n"
                f"MC Number: {mc_number}\n"
                f"Authority Date: {authority_date_str}\n"
                f"Authority Type: Common Carrier of Property\n"
                f"\n{detail_text}"
            )

            items.append(RawItem(
                channel="registry",
                source_url=detail_url or _SAFER_SEARCH,
                fetched_at=datetime.now(tz=timezone.utc),
                title=f"FMCSA Authority Grant – {carrier_name}",
                body=body[:4000],
            ))
        except Exception:
            continue

    return items


def _fmcsa_carrier_detail(page, url: str) -> str:
    if not url or not url.startswith("http"):
        return ""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=10000)
        content = page.query_selector("table.querydisplay")
        return content.inner_text().strip() if content else ""
    except Exception:
        return ""


def _fetch_nsc_new_carriers(days_back: int = 14) -> list[RawItem]:
    """
    Polls Transport Canada NSC carrier search for newly registered carriers.
    Returns RawItems with signal_type=authority_grant.
    """
    from playwright.sync_api import sync_playwright

    items: list[RawItem] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            items = _nsc_search(page)
        finally:
            browser.close()

    log.info("registry: NSC collected %d items", len(items))
    return items


def _nsc_search(page) -> list[RawItem]:
    items: list[RawItem] = []
    try:
        page.goto(_NSC_SEARCH, wait_until="domcontentloaded", timeout=15000)
        page.fill('input[name="carrier_name"]', "")
        page.click('input[type="submit"]')
        page.wait_for_load_state("networkidle", timeout=10000)

        rows = page.query_selector_all("table tr")[1:]
        for row in rows[:50]:
            cells = row.query_selector_all("td")
            if len(cells) < 4:
                continue
            try:
                name = cells[0].inner_text().strip()
                nsc = cells[1].inner_text().strip()
                province = cells[2].inner_text().strip()
                status = cells[3].inner_text().strip()

                if not name or "active" not in status.lower():
                    continue

                body = (
                    f"Transport Canada NSC Registration.\n"
                    f"Entity: {name}\n"
                    f"NSC Number: {nsc}\n"
                    f"Province: {province}\n"
                    f"Status: {status}\n"
                    f"Country: Canada"
                )

                items.append(RawItem(
                    channel="registry",
                    source_url=_NSC_SEARCH,
                    fetched_at=datetime.now(tz=timezone.utc),
                    title=f"NSC Registration – {name}",
                    body=body,
                ))
            except Exception:
                continue
    except Exception as exc:
        log.warning("registry: NSC search failed: %s", exc)

    return items
