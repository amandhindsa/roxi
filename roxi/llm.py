from __future__ import annotations

import logging
import os
import time
from typing import TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from roxi.store import log_llm_call

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_client: anthropic.Anthropic | None = None

# Model name constants — verified 2026-09-04 against console.anthropic.com/docs/models
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"
OPUS = "claude-opus-4-8"

# Pricing per million tokens — verified 2026-09-04 against anthropic.com/pricing
COST_PER_MILLION = {
    HAIKU:  {"input": 1.00, "output": 5.00},
    SONNET: {"input": 3.00, "output": 15.00},
    OPUS:   {"input": 15.00, "output": 75.00},
}


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


class ExtractionError(Exception):
    pass


def _prompt_version(system: str) -> str:
    import hashlib
    return hashlib.sha256(system.encode()).hexdigest()[:12]


def _input_hash(user: str) -> str:
    import hashlib
    return hashlib.sha256(user.encode()).hexdigest()[:12]


def structured(
    *,
    model: str,
    system: str,
    user: str,
    schema: type[T],
    agent: str = "unknown",
    lead_id: str | None = None,
    run_id: str | None = None,
    org_id: str | None = None,
    max_retries: int = 1,
    max_tokens: int = 2048,
) -> T:
    tool_def = {
        "name": schema.__name__,
        "description": f"Emit a {schema.__name__} object.",
        "input_schema": schema.model_json_schema(),
    }

    messages: list[dict] = [{"role": "user", "content": user}]
    last_error: str | None = None
    last_tool_block = None  # carries over between retries to build the correct thread

    for attempt in range(max_retries + 1):
        if last_error and attempt > 0 and last_tool_block is not None:
            # Inject the real tool_use id from the previous attempt — not a hardcoded "retry"
            log.warning(
                "llm: retry %d/%d for %s schema=%s error=%s (run_id=%s)",
                attempt, max_retries, agent, schema.__name__, last_error[:120], run_id,
            )
            messages.append({"role": "assistant", "content": [
                {
                    "type": "tool_use",
                    "id": last_tool_block.id,
                    "name": last_tool_block.name,
                    "input": last_tool_block.input,
                }
            ]})
            messages.append({"role": "user", "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": last_tool_block.id,
                    "content": f"Validation failed: {last_error}. Please fix and re-emit.",
                }
            ]})

        t0 = time.perf_counter()
        try:
            response = _get_client().messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                tools=[tool_def],
                tool_choice={"type": "tool", "name": schema.__name__},
            )
        except anthropic.APIError as exc:
            log.error("llm: APIError in %s schema=%s attempt=%d: %s (run_id=%s)",
                      agent, schema.__name__, attempt, exc, run_id)
            raise ExtractionError(f"APIError: {exc}") from exc

        latency_ms = int((time.perf_counter() - t0) * 1000)
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        rates = COST_PER_MILLION.get(model, {"input": 0, "output": 0})
        cost_usd = (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000

        tool_block = next(
            (b for b in response.content if b.type == "tool_use"),
            None,
        )

        outcome = "ok"
        if tool_block is None:
            outcome = "no_tool_block"
            last_error = "No tool_use block in response"
            log.warning("llm: no tool_use block from %s schema=%s attempt=%d (run_id=%s)",
                        agent, schema.__name__, attempt, run_id)
            _log_call(model, agent, input_tokens, output_tokens, cost_usd, latency_ms,
                      lead_id, run_id, org_id, system, user, outcome)
            continue

        last_tool_block = tool_block
        try:
            result = schema.model_validate(tool_block.input)
            log.debug("llm: %s schema=%s ok in=%d out=%d cost=$%.5f lat=%dms (run_id=%s)",
                      agent, schema.__name__, input_tokens, output_tokens, cost_usd, latency_ms, run_id)
            _log_call(model, agent, input_tokens, output_tokens, cost_usd, latency_ms,
                      lead_id, run_id, org_id, system, user, "ok")
            return result
        except ValidationError as exc:
            outcome = "validation_error"
            last_error = str(exc)
            _log_call(model, agent, input_tokens, output_tokens, cost_usd, latency_ms,
                      lead_id, run_id, org_id, system, user, outcome)

    raise ExtractionError(
        f"Failed to extract {schema.__name__} after {max_retries + 1} attempts: {last_error}"
    )


def _log_call(
    model: str, agent: str, input_tokens: int, output_tokens: int,
    cost_usd: float, latency_ms: int, lead_id: str | None,
    run_id: str | None, org_id: str | None,
    system: str, user: str, outcome: str,
) -> None:
    try:
        log_llm_call(
            model=model,
            agent=agent,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            lead_id=lead_id,
            run_id=run_id,
            org_id=org_id,
            prompt_version=_prompt_version(system),
            input_hash=_input_hash(user),
            outcome=outcome,
        )
    except Exception as exc:
        log.debug("llm: failed to write llm_call row: %s", exc)
