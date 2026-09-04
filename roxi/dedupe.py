from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher

from roxi.models import Signal

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
    if ca.split()[0] == cb.split()[0] and len(ca.split()[0]) >= 4:
        return True
    return SequenceMatcher(None, ca, cb).ratio() >= 0.82


def dedupe(
    signals: list[Signal],
    seen_keys: set[str],
    recent_company_names: list[str],
) -> list[Signal]:
    surviving: list[Signal] = []
    local_keys: set[str] = set()
    local_companies: list[str] = list(recent_company_names)

    for sig in signals:
        key = signal_key(sig)

        if key in seen_keys or key in local_keys:
            continue

        already_seen = any(_fuzzy_match(sig.company, name) for name in local_companies)
        if already_seen:
            continue

        local_keys.add(key)
        local_companies.append(sig.company)
        surviving.append(sig)

    return surviving
