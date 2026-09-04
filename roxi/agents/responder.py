"""
Phase 7 — Responder.

One agent, channel-agnostic. Classifies reply intent and extracts useful details.
Unsubscribe intent is written to the suppression list immediately, before any human
sees the reply — this is not optional.

Input:  inbound message text + the original lead context
Output: ReplyClassification — intent, details, suggested next action
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel

from roxi.llm import HAIKU, ExtractionError, structured
from roxi.models import Lead
from roxi import store

log = logging.getLogger(__name__)

_SYSTEM = """\
You are the Responder for an outbound sales system. You read a reply to a cold email \
and classify the intent. You are channel-agnostic — the same intent labels apply \
to email and SMS replies.

Intent labels:
- interested: the prospect is open to learning more or scheduling a call
- not_now: politely declining for now but not hostile (e.g. "we're mid-cycle", "try me in Q1")
- wrong_person: reply indicates this email reached the wrong individual
- out_of_office: automated OOO or vacation reply
- unsubscribe: any expression of wanting no further contact — explicit OR implicit
  ("stop emailing me", "please remove me", "not interested, don't contact again")
  BE CONSERVATIVE: when in doubt, classify as unsubscribe. A false positive is much
  safer than missing an unsubscribe request.
- hostile: aggressive or threatening language; note carefully
- other: none of the above

For unsubscribe and hostile: these write to the suppression list automatically.
For interested: extract any timing, referral name, or next-step preference mentioned.
For wrong_person: extract the correct contact if named.
"""


class ReplyClassification(BaseModel):
    intent: Literal["interested", "not_now", "wrong_person", "out_of_office", "unsubscribe", "hostile", "other"]
    confidence: Literal["high", "medium", "low"]
    extracted_details: str
    suggested_next_action: str
    suppress: bool


def classify_reply(
    reply_text: str,
    lead: Lead,
    run_id: str | None = None,
) -> ReplyClassification | None:
    context = (
        f"Original outreach:\n"
        f"  Company: {lead.scored.company}\n"
        f"  Subject: {lead.draft.subject if lead.draft else 'unknown'}\n"
        f"  Why now: {lead.scored.evidence}\n\n"
        f"Reply:\n{reply_text}"
    )

    try:
        classification = structured(
            model=HAIKU,
            system=_SYSTEM,
            user=context,
            schema=ReplyClassification,
            agent="responder",
            run_id=run_id,
        )
    except ExtractionError as exc:
        log.error(
            "responder: ExtractionError classifying reply for lead %s company=%r (run_id=%s): %s — "
            "unsubscribe signal may be unprocessed",
            lead.id, lead.scored.company, run_id, exc,
        )
        return None

    log.info(
        "responder: lead=%s company=%r intent=%s confidence=%s suppress=%s (run_id=%s)",
        lead.id, lead.scored.company, classification.intent,
        classification.confidence, classification.suppress, run_id,
    )

    # Unsubscribe and hostile always suppress — do it immediately (compliance critical)
    if classification.suppress or classification.intent in ("unsubscribe", "hostile"):
        contact_id = lead.scored.company_domain or lead.scored.company
        store.add_to_suppression_list(
            contact_identifier=contact_id,
            channel="email",
            reason=f"responder:{classification.intent}",
        )
        log.info(
            "responder: suppressed %r on email — intent=%s (lead=%s)",
            contact_id, classification.intent, lead.id,
        )
        store.update_status(lead.id, "replied")

    if classification.intent == "interested":
        store.update_status(lead.id, "replied")

    return classification
