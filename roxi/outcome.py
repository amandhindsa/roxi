from __future__ import annotations

from roxi import store


def mark_sent(lead_id: str) -> None:
    store.update_status(lead_id, "sent")


def mark_replied(lead_id: str) -> None:
    store.update_status(lead_id, "replied")
