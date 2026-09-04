"""
Compiler — setup agent that interviews a user and writes a VerticalConfig.

Runs once, with a person present. Output is reviewable plain text before
anything is written to disk. This is the only agent whose output a human edits.

Usage:
  python -m roxi compile
  python -m roxi compile --output verticals/my_vertical.yaml
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import anthropic
import yaml
from pydantic import BaseModel, ValidationError

from roxi.config import (
    ChannelJobBoards, ChannelReddit, ChannelRegistry, ChannelsConfig,
    ICPConfig, ModelsConfig, ScoringRule, VerticalConfig,
)
from roxi.llm import COST_PER_MILLION, HAIKU, SONNET, _get_client
from roxi import store

log = logging.getLogger(__name__)

_INTERVIEW_SYSTEM = """\
You are the Compiler for Roxi, a B2B lead generation platform. Your job is to interview \
a user about their product and buyer, then write a working vertical configuration. \
You run once, with the user present.

You have web search available. Use it to read the user's website and understand their market.

Interview process:
1. Ask for the product description and website URL.
2. Search the website to understand what they actually sell and to whom.
3. Ask targeted clarifying questions — focus on:
   - What does a bad customer look like? (Disqualifiers are where most accuracy lives.)
   - What specific, observable, public signals indicate a company is about to buy?
   - What channels produce those signals? (Job boards, regulatory filings, forums?)
4. Draft the config and present it in plain English for review.

Rules for the config you produce:
- Every scoring rule must be checkable against a single signal field. No vague rules.
- Disqualifiers must be unambiguous. "Too small" is not a disqualifier. "Fewer than 8 trucks" is.
- Propose numeric deltas — if you are uncertain about the weight, say so and explain why.
- Select only channels that have observable, public signals for this domain.
- Warn if a domain has no publicly observable buying signals rather than shipping a bad first run.
- qualify_threshold: 70 unless there is a clear reason to differ.

Output format: when you are ready to emit the config, call the EmitVerticalConfig tool.
"""


class _EmittedConfig(BaseModel):
    vertical_id: str
    product_brief: str
    icp_description: str
    disqualifiers: list[str]
    scoring_rules: list[dict]
    qualify_threshold: int = 70
    job_boards_enabled: bool = True
    job_board_queries: list[str] = []
    registry_enabled: bool = False
    reddit_enabled: bool = False
    reddit_subreddits: list[str] = []
    extractor_model: str = HAIKU
    scorer_model: str = HAIKU
    researcher_model: str = SONNET
    drafter_model: str = SONNET
    daily_research_budget: int = 15
    notes_for_user: str = ""


def run_compiler(output_path: str | None = None) -> VerticalConfig:
    """
    Interactive compiler session. Returns the confirmed VerticalConfig.
    Writes YAML to output_path if provided.
    """
    print("\nRoxi Compiler — setting up a new vertical")
    print("─" * 56)
    print("I'll interview you about your product and buyer, search")
    print("your website, and draft a vertical config for review.")
    print("Type your answers below. Press Ctrl-C to cancel.\n")

    product_desc = _prompt("Describe your product and who buys it (1-3 sentences):\n> ")
    website_url = _prompt("Your website URL (I'll read it to understand your market):\n> ").strip()

    print("\nSearching your website and researching the market…\n")

    client = _get_client()
    messages: list[dict] = [
        {"role": "user", "content": (
            f"Product description: {product_desc}\n"
            f"Website: {website_url}\n\n"
            "Please search the website, then ask me the clarifying questions you need "
            "to write a working vertical config."
        )}
    ]

    total_input_tokens = 0
    total_output_tokens = 0
    model = SONNET

    while True:
        t0 = time.perf_counter()
        response = client.messages.create(
            model=model,
            max_tokens=2000,
            system=_INTERVIEW_SYSTEM,
            messages=messages,
            tools=[
                {"type": "web_search_20250305", "name": "web_search"},
                {
                    "name": "EmitVerticalConfig",
                    "description": "Emit the completed vertical config when the interview is done.",
                    "input_schema": _EmittedConfig.model_json_schema(),
                },
            ],
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        # Log this turn's cost
        rates = COST_PER_MILLION.get(model, {"input": 0, "output": 0})
        turn_cost = (
            response.usage.input_tokens * rates["input"]
            + response.usage.output_tokens * rates["output"]
        ) / 1_000_000
        try:
            store.log_llm_call(
                model=model,
                agent="compiler",
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cost_usd=turn_cost,
                latency_ms=latency_ms,
                lead_id=None,
            )
        except Exception as exc:
            log.debug("compiler: failed to log turn cost: %s", exc)

        # Collect text and tool blocks
        text_parts = []
        emit_block = None

        for block in response.content:
            if hasattr(block, "text") and block.text:
                text_parts.append(block.text)
            if block.type == "tool_use" and block.name == "EmitVerticalConfig":
                emit_block = block

        if text_parts:
            print("\n" + "\n".join(text_parts))

        if emit_block:
            try:
                emitted = _EmittedConfig.model_validate(emit_block.input)
            except ValidationError as exc:
                print(f"\nConfig validation error: {exc}")
                print("Please describe what to fix:")
                fix = _prompt("> ")
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": emit_block.id,
                     "content": f"Validation failed: {exc}. {fix}"}
                ]})
                continue

            vertical = _emitted_to_vertical(emitted)
            yaml_str = _vertical_to_yaml(emitted)

            print("\n" + "─" * 56)
            print("Proposed vertical config (YAML):")
            print("─" * 56)
            print(yaml_str)
            if emitted.notes_for_user:
                print(f"\nNotes: {emitted.notes_for_user}")
            rates = COST_PER_MILLION.get(model, {"input": 0, "output": 0})
            total_cost = (total_input_tokens * rates["input"] + total_output_tokens * rates["output"]) / 1_000_000
            print(f"\nSession tokens: {total_input_tokens + total_output_tokens:,}  cost: ${total_cost:.4f}")
            print("─" * 56)

            action = _prompt("\n[a]ccept / [e]dit and re-run / [q]uit: ").strip().lower()
            if action.startswith("a"):
                if output_path:
                    Path(output_path).write_text(yaml_str)
                    print(f"\nWritten to {output_path}")
                else:
                    suggested = f"verticals/{emitted.vertical_id}.yaml"
                    write_it = _prompt(f"Write to {suggested}? [y/n]: ").strip().lower()
                    if write_it.startswith("y"):
                        Path(suggested).write_text(yaml_str)
                        print(f"Written to {suggested}")
                log.info("compiler: vertical %s accepted (tokens=%d cost=$%.4f)",
                         emitted.vertical_id, total_input_tokens + total_output_tokens, total_cost)
                return vertical
            elif action.startswith("q"):
                sys.exit(0)
            else:
                feedback = _prompt("What should change? Describe in plain English:\n> ")
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": emit_block.id,
                     "content": f"User rejected this config. Feedback: {feedback}"}
                ]})
                continue

        # Web search tool_use blocks are handled server-side by Anthropic's API.
        # Their results are already embedded in response.content as tool_result blocks.
        # Never inject fake tool_results for web_search — it overrides what the API returned.
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            # Model asked a question — wait for user reply
            user_reply = _prompt("> ")
            messages.append({"role": "user", "content": user_reply})
        elif response.stop_reason == "tool_use":
            # web_search tool_use: the API already handled it and embedded results in content.
            # For EmitVerticalConfig: handled above. Just continue the loop.
            pass


def _prompt(text: str) -> str:
    try:
        return input(text)
    except EOFError:
        sys.exit(0)


def _emitted_to_vertical(e: _EmittedConfig) -> VerticalConfig:
    rules = [ScoringRule(rule=r["rule"], delta=r["delta"]) for r in e.scoring_rules]
    return VerticalConfig(
        vertical_id=e.vertical_id,
        product_brief=e.product_brief,
        icp=ICPConfig(description=e.icp_description, disqualifiers=e.disqualifiers),
        scoring_rules=rules,
        qualify_threshold=e.qualify_threshold,
        channels=ChannelsConfig(
            job_boards=ChannelJobBoards(enabled=e.job_boards_enabled, queries=e.job_board_queries),
            registry=ChannelRegistry(enabled=e.registry_enabled),
            reddit=ChannelReddit(enabled=e.reddit_enabled, subreddits=e.reddit_subreddits),
        ),
        models=ModelsConfig(
            extractor=e.extractor_model,
            scorer=e.scorer_model,
            researcher=e.researcher_model,
            drafter=e.drafter_model,
        ),
        daily_research_budget=e.daily_research_budget,
    )


def _vertical_to_yaml(e: _EmittedConfig) -> str:
    data = {
        "vertical_id": e.vertical_id,
        "product_brief": e.product_brief,
        "icp": {"description": e.icp_description, "disqualifiers": e.disqualifiers},
        "scoring_rules": e.scoring_rules,
        "qualify_threshold": e.qualify_threshold,
        "channels": {
            "job_boards": {"enabled": e.job_boards_enabled, "queries": e.job_board_queries},
            "registry": {"enabled": e.registry_enabled},
            "reddit": {"enabled": e.reddit_enabled, "subreddits": e.reddit_subreddits},
        },
        "models": {
            "extractor": e.extractor_model,
            "scorer": e.scorer_model,
            "researcher": e.researcher_model,
            "drafter": e.drafter_model,
        },
        "daily_research_budget": e.daily_research_budget,
    }
    return yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
