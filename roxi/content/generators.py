"""
Phase 8 — Generators.

Adapters only — no model. Call external generation APIs.
Each generator is deterministic with retries; they do not make creative decisions.

Text generation is free (the Director wrote the copy). These adapters handle image
and video, which cost money and time, and run only on approved Director briefs.
"""

from __future__ import annotations

import logging
import os
import time
import uuid as _uuid_mod
from pathlib import Path

from roxi.content.models import DirectorBrief, GeneratedAsset

# Where to persist images. Override with ROXI_ASSET_DIR env var.
# In production, point this at a mounted object storage volume or configure
# a real S3/R2/Supabase-Storage adapter.
_ASSET_DIR = Path(os.environ.get("ROXI_ASSET_DIR", "assets/generated"))

log = logging.getLogger(__name__)

_IMAGE_COST_USD = 0.08  # DALL-E 3 standard quality, 1792x1024


def generate(brief: DirectorBrief, max_retries: int = 3) -> GeneratedAsset | None:
    if brief.media_type == "text":
        return _generate_text(brief)
    elif brief.media_type == "image":
        return _generate_image(brief, max_retries)
    elif brief.media_type == "video":
        return _generate_video(brief, max_retries)
    log.warning("generators: unknown media_type %r for item %s", brief.media_type, brief.item_id)
    return None


def _generate_text(brief: DirectorBrief) -> GeneratedAsset:
    log.info("generators: text asset ready for item %s platform=%s", brief.item_id, brief.platform)
    return GeneratedAsset(
        item_id=brief.item_id,
        media_type="text",
        text_content=brief.copy,
        generation_cost_usd=0.0,
        provider="director",
    )


def _generate_image(brief: DirectorBrief, max_retries: int) -> GeneratedAsset | None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY required for image generation")

    import requests

    for attempt in range(max_retries):
        try:
            t0 = time.perf_counter()
            r = requests.post(
                "https://api.openai.com/v1/images/generations",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "dall-e-3",
                    "prompt": brief.image_prompt,
                    "n": 1,
                    "size": "1792x1024",
                    "quality": "standard",
                },
                timeout=60,
            )
            r.raise_for_status()
            latency_ms = int((time.perf_counter() - t0) * 1000)
            data_items = r.json().get("data", [])
            if not data_items:
                raise ValueError("OpenAI returned empty data array — content policy refusal")
            # OpenAI returns a signed S3 URL that expires in ~60 minutes.
            # Download and persist immediately so publishers have a permanent URL.
            ephemeral_url = data_items[0]["url"]
            permanent_url = _download_and_store(ephemeral_url, brief.item_id)
            log.info("generators: image for item %s in %dms cost=$%.2f stored=%s",
                     brief.item_id, latency_ms, _IMAGE_COST_USD, permanent_url)
            _record_image_cost(brief.item_id, _IMAGE_COST_USD)
            return GeneratedAsset(
                item_id=brief.item_id,
                media_type="image",
                url=permanent_url,
                generation_cost_usd=_IMAGE_COST_USD,
                provider="openai/dall-e-3",
            )
        except Exception as exc:
            log.warning("generators: image attempt %d/%d failed for item %s: %s",
                        attempt + 1, max_retries, brief.item_id, exc)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise exc
    return None


def _generate_video(brief: DirectorBrief, max_retries: int) -> GeneratedAsset | None:
    """
    Video generation via HeyGen HyperFrames.
    Evaluate before building the full assembly pipeline — HyperFrames may handle
    the script-to-rendered-video chain entirely, removing the need to build this.

    This stub raises NotImplementedError until HyperFrames is evaluated.
    Per doc 08: video requires its own async job queue with per-asset spend caps
    and resumable stages. Do not implement as a synchronous pipeline step.
    """
    log.error("generators: video generation requested for item %s but not yet implemented", brief.item_id)
    raise NotImplementedError(
        "Video generation requires an async job queue with per-asset spend caps. "
        "Evaluate HyperFrames before building (see doc 08 §3)."
    )


def _download_and_store(url: str, item_id: str) -> str:
    """
    Downloads the image from a temporary URL and saves it to _ASSET_DIR.
    Returns a file:// path (or configurable public URL prefix via ROXI_ASSET_BASE_URL).
    In production, replace this with an upload to S3/R2/Supabase Storage and return
    the permanent public URL.
    """
    import requests
    _ASSET_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{item_id}_{_uuid_mod.uuid4().hex[:8]}.png"
    dest = _ASSET_DIR / filename
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    dest.write_bytes(r.content)
    base = os.environ.get("ROXI_ASSET_BASE_URL", "")
    return f"{base}/{filename}" if base else str(dest.resolve())


def _record_image_cost(item_id: str, cost_usd: float) -> None:
    """Write image generation cost via the store's public API (init_db owns the schema)."""
    try:
        from roxi import store
        import uuid as _uuid

        store.record_generation_cost(
            item_id=item_id,
            provider="openai/dall-e-3",
            cost_usd=cost_usd,
        )
    except Exception as exc:
        log.warning("generators: failed to record image cost for %s: %s", item_id, exc)
