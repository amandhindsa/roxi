from __future__ import annotations

import hashlib
import logging
import re
from difflib import SequenceMatcher

from roxi.models import Signal

log = logging.getLogger(__name__)

_CORP_SUFFIXES = re.compile(
    r"\b(ltd|limited|inc|incorporated|corp|corporation|lp|llc|co|company|"
    r"transport|transportation|trucking|logistics|freight|carriers?|"
    r"express|lines?|group|enterprises?|services?|solutions?)\b",
    re.IGNORECASE,
)
_PUNCT = re.compile(r"[^a-z0-9 ]")


def _canonical(name: str) -> str:
    name = name.lower()
    name = _CORP_SUFFIXES.sub("", name)
    name = _PUNCT.sub("", name)
    return " ".join(name.split())


def signal_key(signal: Signal) -> str:
    raw = f"{_canonical(signal.company)}:{signal.signal_type}:{signal.evidence[:80]}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _fuzzy_match(a: str, b: str) -> bool:
    ca, cb = _canonical(a), _canonical(b)
    if not ca or not cb:
        return False
    ca_tokens, cb_tokens = ca.split(), cb.split()
    # First-token shortcut: only when both sides have >1 meaningful token after stripping.
    # Single-token canonicals (e.g. both "Pacific Freight" and "Pacific Logistics" → "pacific")
    # must NOT be matched this way — they need at least 2 tokens to signal a genuine shared root.
    if (
        len(ca_tokens) > 1
        and len(cb_tokens) > 1
        and ca_tokens[0] == cb_tokens[0]
        and len(ca_tokens[0]) >= 4
    ):
        return True
    # SequenceMatcher fallback: require both sides to have >1 token before allowing a high-ratio
    # match. Two identical single-token strings (ratio=1.0) would otherwise always merge, defeating
    # the suffix-stripping guard above for names like "Pacific Freight" vs "Pacific Logistics".
    if len(ca_tokens) < 2 or len(cb_tokens) < 2:
        return False
    return SequenceMatcher(None, ca, cb).ratio() >= 0.82


def dedupe_exact(signals: list[Signal], seen_keys: set[str]) -> list[Signal]:
    """Remove signals whose exact key has been seen before (cross-run or within-run)."""
    surviving: list[Signal] = []
    local_keys: set[str] = set()
    for sig in signals:
        key = signal_key(sig)
        if key in seen_keys or key in local_keys:
            continue
        local_keys.add(key)
        surviving.append(sig)
    return surviving


def dedupe_company(
    signals: list[Signal],
    recent_company_names: list[str],
) -> list[Signal]:
    """Remove signals for companies already contacted recently, keeping highest-score when
    multiple signals for the same company compete within this run.

    Signals must already be sorted highest-score first so that the winner is the first one
    seen for each company.
    """
    surviving: list[Signal] = []
    local_companies: list[str] = list(recent_company_names)

    for sig in signals:
        already_seen = any(_fuzzy_match(sig.company, name) for name in local_companies)
        if already_seen:
            log.debug(
                "dedupe: dropped %r — fuzzy match against existing company", sig.company
            )
            continue
        local_companies.append(sig.company)
        surviving.append(sig)

    return surviving


def dedupe(
    signals: list[Signal],
    seen_keys: set[str],
    recent_company_names: list[str],
) -> list[Signal]:
    """Legacy entry point used by callers that score after deduping.

    Prefer calling dedupe_exact + score + sort + dedupe_company directly.
    """
    after_exact = dedupe_exact(signals, seen_keys)
    return dedupe_company(after_exact, recent_company_names)
