from __future__ import annotations

from roxi.store import update_status


def mark_sent(lead_id: str) -> None:
    update_status(lead_id, "sent")


def mark_replied(lead_id: str) -> None:
    update_status(lead_id, "replied")
