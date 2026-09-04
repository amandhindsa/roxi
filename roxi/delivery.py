from __future__ import annotations

import json
import logging
import os

import requests

from roxi.models import Lead

log = logging.getLogger(__name__)


def deliver(leads: list[Lead], vertical_id: str) -> None:
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        log.warning("SLACK_WEBHOOK_URL not set — %d leads not delivered", len(leads))
        return

    for lead in leads:
        _post_card(lead, vertical_id, webhook_url)


def _post_card(lead: Lead, vertical_id: str, webhook_url: str) -> None:
    scored = lead.scored
    draft = lead.draft

    why_now = draft.why_now if draft else scored.evidence[:200]
    subject = draft.subject if draft else "(no draft)"

    text = (
        f"*{scored.company}* — {scored.location or 'location unknown'} — "
        f"score *{scored.score}/100*\n"
        f"*Why now:* {why_now}\n"
        f"*Evidence:* \"{scored.evidence}\"\n"
        f"*Draft subject:* {subject}\n"
        f"*Lead ID:* `{lead.id}`"
    )

    payload = {
        "text": text,
        "attachments": [
            {
                "fallback": "Approve or reject this lead",
                "callback_id": lead.id,
                "actions": [
                    {
                        "name": "decision",
                        "text": "Approve",
                        "type": "button",
                        "value": "approved",
                        "style": "primary",
                    },
                    {
                        "name": "decision",
                        "text": "Reject",
                        "type": "button",
                        "value": "rejected",
                        "style": "danger",
                    },
                ],
            }
        ],
    }

    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        r.raise_for_status()
        log.info("Slack card posted for lead %s", lead.id)
    except requests.RequestException as exc:
        log.error("Slack post failed for lead %s: %s", lead.id, exc)
