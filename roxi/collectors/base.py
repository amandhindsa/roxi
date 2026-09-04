from __future__ import annotations

from typing import Protocol

from roxi.config import VerticalConfig
from roxi.models import RawItem


class Collector(Protocol):
    def fetch(self, vertical: VerticalConfig) -> list[RawItem]: ...
