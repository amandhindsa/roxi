"""
Onboarding interview agent.

Conducts a multi-turn conversation to understand what the customer sells
and who their ideal customer is. Produces a draft VerticalConfig expressed
in plain English, then loops until the customer accepts.

State machine:
  intro → product → buyer → bad_fit_check → signals → thresholds → draft → revise → complete

When state='complete', returns a VerticalRules object ready to save.

Public API
----------
    reply, updated_session, rules = advance_session(session, user_message)

    - reply           : str — the assistant's next message (display to user)
    - updated_session : SetupSession — mutated copy with new messages and state
    - rules           : VerticalRules | None — set only when state='complete'
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import anthropic

from roxi.llm import SONNET, _get_client, structured
from roxi.models import SetupMessage, SetupSession, VerticalRules

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are the Roxi onboarding assistant. Roxi is a B2B lead generation service: \
it monitors public signals (job postings, company registry changes, forum posts) \
and surfaces companies that are likely to buy what our customer sells.

Your job is to conduct a focused onboarding interview. You need to collect exactly \
the information Roxi needs to configure a lead-finding pipeline. Be warm but \
efficient — this should feel like a 10-minute call, not an interrogation.

## What you must learn (in roughly this order)

1. **Product & buyer** — What does the customer sell? Who is the decision-maker? \
   What industry/company type buys it?

2. **Website** — Ask for their website URL so you can read their positioning \
   (you won't actually fetch it — just acknowledge it and use the information they give you).

3. **Bad-fit customers** — What kinds of companies should we explicitly skip? \
   (wrong size, wrong industry, consumer-facing, already a competitor, etc.)

4. **Buying signals** — What public events signal a company is likely to buy soon? \
   Examples: hiring a specific role, receiving funding, filing for an authority, \
   posting about a specific pain. If their industry has no obvious public signals, \
   say so honestly and ask what they observe in their own sales calls.

5. **Volume & threshold** — How many qualified leads per day do they want? \
   How conservative should we be (fewer high-quality vs. more at lower certainty)?

## When to draft

After you have collected answers to all five areas (typically ~5 user messages), \
produce a plain-English draft summary in this exact format:

---
**Draft configuration**

We will look for: [one sentence describing the ideal company and situation]

We will skip: [bullet list of disqualifiers]

Scoring signals:
- [signal description] → +[points] pts
- [signal description] → +[points] pts
- [disqualifying signal] → disqualified

Minimum score to qualify: [N] out of 100

Daily lead target: [N] leads/day
---

Then ask: "Does this look right? If anything is off, just tell me and I'll adjust."

## Revision loop

If the customer asks for changes, apply them to the draft and re-present it using \
the same format. Repeat until they say something like "yes", "looks good", \
"that's correct", "perfect", etc.

## Completion

When the customer approves the draft, respond with a brief confirmation message \
that ends with the exact marker: [SETUP_COMPLETE]

## Important constraints

- Never invent company names, signal counts, or statistics.
- If the customer's industry genuinely has few public signals (e.g. private dental \
  practices, sole-trader plumbers), say so honestly. Suggest what we can do: \
  monitor hiring of relevant staff, watch for business registry new-entrant filings, etc.
- Keep responses concise. Avoid walls of text. Use bullets where helpful.
- Do not ask all questions at once — advance one topic at a time based on what \
  they've answered.
- Always be specific: "hiring a Director of Logistics" is better than "hiring someone".
- Points allocation guidance: a single strong signal is typically worth 30-50 pts; \
  supporting signals 10-20 pts each; qualify_threshold default is 70.
"""

# ---------------------------------------------------------------------------
# Structured extraction schemas
# ---------------------------------------------------------------------------

from pydantic import BaseModel, Field


class _ScoringRuleExtract(BaseModel):
    rule: str
    delta: int | str  # int for points; "disqualify" for hard stops


class _ICPExtract(BaseModel):
    description: str
    disqualifiers: list[str]


class _RulesExtract(BaseModel):
    product_brief: str = Field(description="One paragraph describing what the customer sells and to whom.")
    icp: _ICPExtract
    scoring_rules: list[_ScoringRuleExtract]
    qualify_threshold: int = Field(ge=0, le=100)
    daily_lead_target: int = Field(ge=1, le=100, default=5)
    summary: str = Field(
        description=(
            "The plain-English draft summary shown to the customer. "
            "Use the exact 'Draft configuration' format from the instructions."
        )
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _messages_to_anthropic(messages: list[SetupMessage]) -> list[dict]:
    """Convert SetupMessage list to the Anthropic messages format."""
    return [{"role": m.role, "content": m.content} for m in messages]


def _call_llm(messages: list[dict], max_tokens: int = 1024) -> tuple[str, int, int]:
    """Make a plain (non-structured) chat call. Returns (text, input_tokens, output_tokens)."""
    client = _get_client()
    t0 = time.perf_counter()
    try:
        response = client.messages.create(
            model=SONNET,
            max_tokens=max_tokens,
            system=_SYSTEM_PROMPT,
            messages=messages,
        )
    except anthropic.APIError as exc:
        log.error("interviewer: APIError: %s", exc)
        raise

    latency_ms = int((time.perf_counter() - t0) * 1000)
    text = "".join(
        block.text for block in response.content if hasattr(block, "text")
    )
    input_tok = response.usage.input_tokens
    output_tok = response.usage.output_tokens
    log.debug(
        "interviewer: in=%d out=%d lat=%dms",
        input_tok, output_tok, latency_ms,
    )
    return text, input_tok, output_tok


def _build_rules_from_conversation(
    messages: list[SetupMessage],
    subscription_id: str,
    existing_version: int = 0,
) -> VerticalRules:
    """Extract structured rules from the completed interview conversation.

    Calls the LLM with a structured tool to parse the full message history
    and produce a VerticalRules object.

    Args:
        messages: Full conversation history including the final approval.
        subscription_id: The subscription this config belongs to.
        existing_version: The previous rules version; new version = existing_version + 1.

    Returns:
        A VerticalRules instance (not yet persisted — caller saves it).
    """
    conversation_text = "\n\n".join(
        f"{'Customer' if m.role == 'user' else 'Roxi'}: {m.content}"
        for m in messages
    )

    extraction_prompt = (
        "Here is the completed onboarding conversation:\n\n"
        f"{conversation_text}\n\n"
        "Extract the final agreed configuration into the _RulesExtract schema. "
        "Use the last approved draft if the customer made revisions. "
        "For scoring_rules.delta, use an integer for positive/negative point deltas "
        'or the string "disqualify" for hard-stop rules.'
    )

    extracted: _RulesExtract = structured(
        model=SONNET,
        system=(
            "You are extracting a structured lead-generation configuration from an "
            "onboarding conversation. Be precise. Use only what was agreed in the conversation."
        ),
        user=extraction_prompt,
        schema=_RulesExtract,
        agent="interviewer/extract",
        max_tokens=2048,
    )

    # Serialise to the JSON blobs VerticalRules stores
    rules_list = [
        {"rule": r.rule, "delta": r.delta}
        for r in extracted.scoring_rules
    ]
    icp_dict = {
        "description": extracted.icp.description,
        "disqualifiers": extracted.icp.disqualifiers,
    }

    return VerticalRules(
        subscription_id=subscription_id,
        version=existing_version + 1,
        rules_json=json.dumps(rules_list),
        icp_json=json.dumps(icp_dict),
        product_brief=extracted.product_brief,
        summary=extracted.summary,
        created_at=datetime.now(timezone.utc),
    )


def _is_approval(text: str) -> bool:
    """Heuristic: did the customer approve the draft?"""
    lowered = text.lower().strip()
    approval_phrases = [
        "yes", "yep", "yup", "yeah", "correct", "looks good", "looks right",
        "that's right", "that's correct", "perfect", "great", "approved",
        "sounds good", "sounds right", "go ahead", "let's go", "proceed",
        "that works", "good to go", "all good", "spot on",
    ]
    return any(phrase in lowered for phrase in approval_phrases)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def advance_session(
    session: SetupSession,
    user_message: str,
) -> tuple[str, SetupSession, VerticalRules | None]:
    """Advance the onboarding interview by one user turn.

    Args:
        session: The current SetupSession (not mutated; a copy is returned).
        user_message: The latest message from the customer.

    Returns:
        A 3-tuple:
          - assistant_reply (str): The message to display to the customer.
          - updated_session (SetupSession): Session with new messages appended
            and state updated.
          - rules (VerticalRules | None): Populated only when state='complete';
            None otherwise.
    """
    if session.state == "complete":
        # Idempotent: already done
        return (
            "Your setup is already complete. You can start a new session if you'd "
            "like to configure a different vertical.",
            session,
            None,
        )

    if session.state == "abandoned":
        return (
            "This setup session was abandoned. Please start a new one.",
            session,
            None,
        )

    # Build updated message list
    new_messages = list(session.messages) + [SetupMessage(role="user", content=user_message)]

    # Call the LLM with the full history
    anthropic_messages = _messages_to_anthropic(new_messages)
    try:
        reply_text, _in, _out = _call_llm(anthropic_messages)
    except anthropic.APIError as exc:
        error_reply = (
            "I'm having trouble connecting right now. Please try again in a moment. "
            f"(Error: {exc})"
        )
        # Don't append the failed assistant turn — let the user retry
        updated = session.model_copy(
            update={
                "messages": new_messages,  # user message is kept
                "updated_at": datetime.now(timezone.utc),
            }
        )
        return error_reply, updated, None

    # Append assistant reply to history
    new_messages.append(SetupMessage(role="assistant", content=reply_text))

    # Detect completion marker
    rules: VerticalRules | None = None
    new_state = session.state

    if "[SETUP_COMPLETE]" in reply_text:
        new_state = "complete"
        # Strip the marker from what we show the customer
        reply_text = reply_text.replace("[SETUP_COMPLETE]", "").strip()

        # Extract structured rules from the full conversation
        existing_version = 0
        try:
            rules = _build_rules_from_conversation(
                new_messages,
                subscription_id=session.subscription_id or "",
                existing_version=existing_version,
            )
            log.info(
                "interviewer: setup complete for session %s — rules v%d extracted",
                session.id, rules.version,
            )
        except Exception as exc:
            log.error(
                "interviewer: failed to extract rules for session %s: %s",
                session.id, exc, exc_info=True,
            )
            # Don't block completion — surface the error to the caller via log;
            # rules will be None and the API layer can retry extraction.
            new_state = "active"  # stay active so the user can re-confirm

    updated_session = session.model_copy(
        update={
            "messages": new_messages,
            "state": new_state,
            "updated_at": datetime.now(timezone.utc),
        }
    )

    return reply_text, updated_session, rules
