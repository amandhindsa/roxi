from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel


class ICPConfig(BaseModel):
    description: str
    disqualifiers: list[str]


class ScoringRule(BaseModel):
    rule: str
    delta: int | Literal["disqualify"]


class ChannelJobBoards(BaseModel):
    enabled: bool = False
    queries: list[str] = []


class ChannelRegistry(BaseModel):
    enabled: bool = False


class ChannelReddit(BaseModel):
    enabled: bool = False
    subreddits: list[str] = []


class ChannelsConfig(BaseModel):
    job_boards: ChannelJobBoards = ChannelJobBoards()
    registry: ChannelRegistry = ChannelRegistry()
    reddit: ChannelReddit = ChannelReddit()


class ModelsConfig(BaseModel):
    extractor: str = "claude-haiku-4-5-20251001"   # see roxi.llm.HAIKU
    scorer: str = "claude-haiku-4-5-20251001"       # see roxi.llm.HAIKU
    researcher: str = "claude-sonnet-4-6"           # see roxi.llm.SONNET
    drafter: str = "claude-sonnet-4-6"              # see roxi.llm.SONNET


class VerticalConfig(BaseModel):
    vertical_id: str
    product_brief: str
    icp: ICPConfig
    scoring_rules: list[ScoringRule]
    qualify_threshold: int = 70
    channels: ChannelsConfig = ChannelsConfig()
    models: ModelsConfig = ModelsConfig()
    daily_research_budget: int = 15


def load_vertical(path: str | Path) -> VerticalConfig:
    raw = yaml.safe_load(Path(path).read_text())
    return VerticalConfig.model_validate(raw)
