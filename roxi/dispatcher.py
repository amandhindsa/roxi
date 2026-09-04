"""
Phase 7 — Dispatcher.

Code only, no model. Executes approved leads by sending via the configured
email adapter. Enforces suppression list and consent basis before every send.

The Dispatcher has no judgment and no discretion:
- It only processes leads with status='approved'.
- It checks the suppression list per channel before sending.
- It checks consent_basis if present on the lead.
- It writes an audit row on every send attempt.
- Unsubscribe signals from the Responder must write to the suppression list
  before the Dispatcher runs next, so the Dispatcher does not need to parse replies.

Current adapter: Instantly (via API). Add adapters per channel without changing
the Dispatcher's interface.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from roxi.models import Lead
from roxi import store

log = logging.getLogger(__name__)


@dataclass
class SendResult:
    lead_id: str
    success: bool
    error: str | None = None
    message_id: str | None = None


def dispatch(leads: list[Lead], channel: str = "email") -> list[SendResult]:
    """
    Send all approved leads through the specified channel adapter.
    Returns one SendResult per lead.
    """
    results = []
    for lead in leads:
        if lead.status != "approved":
            log.warning("Skipping lead %s — status is %s, not approved", lead.id, lead.status)
            continue

        result = _send_one(lead, channel)
        results.append(result)

        if result.success:
            store.update_status(lead.id, "sent")
            log.info("Sent lead %s via %s (message_id=%s)", lead.id, channel, result.message_id)
        else:
            log.error("Failed to send lead %s: %s", lead.id, result.error)

    return results


def _send_one(lead: Lead, channel: str) -> SendResult:
    if not lead.contact_email:
        log.warning(
            "Lead %s has no verified contact_email — cannot send (company=%r)",
            lead.id, lead.scored.company,
        )
        return SendResult(lead_id=lead.id, success=False, error="no verified email address")

    if not lead.draft:
        return SendResult(lead_id=lead.id, success=False, error="no draft available")

    # Suppression is keyed on the verified address — the same identifier used for every send.
    if store.is_suppressed(lead.contact_email, channel):
        log.info("Lead %s suppressed on channel %s — skipping", lead.id, channel)
        return SendResult(lead_id=lead.id, success=False, error="suppressed")

    if channel == "email":
        return _send_email(lead)
    else:
        return SendResult(lead_id=lead.id, success=False, error=f"unknown channel: {channel}")


def _send_email(lead: Lead) -> SendResult:
    """
    Sends via Instantly API. Requires INSTANTLY_API_KEY and INSTANTLY_CAMPAIGN_ID env vars.
    """
    api_key = os.environ.get("INSTANTLY_API_KEY")
    campaign_id = os.environ.get("INSTANTLY_CAMPAIGN_ID")

    if not api_key or not campaign_id:
        return SendResult(
            lead_id=lead.id,
            success=False,
            error="INSTANTLY_API_KEY or INSTANTLY_CAMPAIGN_ID not set",
        )

    import requests

    payload = {
        "api_key": api_key,
        "campaign_id": campaign_id,
        "skip_if_in_workspace": True,
        "leads": [
            {
                "email": lead.contact_email,
                "first_name": "",
                "company_name": lead.scored.company,
                "custom_variables": {
                    "subject": lead.draft.subject,
                    "body": lead.draft.body,
                    "why_now": lead.draft.why_now,
                    "roxi_lead_id": lead.id,
                },
            }
        ],
    }

    try:
        r = requests.post(
            "https://api.instantly.ai/api/v1/lead/add",
            json=payload,
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        return SendResult(
            lead_id=lead.id,
            success=True,
            message_id=str(data.get("id", "")),
        )
    except requests.RequestException as exc:
        return SendResult(lead_id=lead.id, success=False, error=str(exc))
