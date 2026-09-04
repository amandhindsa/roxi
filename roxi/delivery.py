from __future__ import annotations

import logging
import os

from roxi.models import Lead

log = logging.getLogger(__name__)


def deliver(leads: list[Lead], vertical_id: str) -> None:
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_WHATSAPP_FROM")  # e.g. "whatsapp:+14155238886"
    to_number = os.environ.get("WHATSAPP_TO")             # e.g. "whatsapp:+16505551234"

    if not all([account_sid, auth_token, from_number, to_number]):
        log.warning(
            "WhatsApp not configured (need TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, "
            "TWILIO_WHATSAPP_FROM, WHATSAPP_TO) — %d leads not delivered",
            len(leads),
        )
        return

    for lead in leads:
        _send_message(lead, vertical_id, account_sid, auth_token, from_number, to_number)


def _send_message(
    lead: Lead,
    vertical_id: str,
    account_sid: str,
    auth_token: str,
    from_number: str,
    to_number: str,
) -> None:
    scored = lead.scored
    draft = lead.draft

    why_now = draft.why_now if draft else scored.evidence[:200]
    subject = draft.subject if draft else "(no draft)"
    short_id = lead.id[:8]

    body = (
        f"🎯 *{scored.company}* — {scored.location or 'unknown location'} — score {scored.score}/100\n"
        f"*Why now:* {why_now}\n"
        f"*Draft subject:* {subject}\n\n"
        f"Reply *approve {short_id}* or *reject {short_id}*"
    )

    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        message = client.messages.create(
            body=body,
            from_=from_number,
            to=to_number,
        )
        log.info("WhatsApp message sent for lead %s (sid=%s)", lead.id, message.sid)
    except Exception as exc:
        log.error("WhatsApp delivery failed for lead %s: %s", lead.id, exc)
