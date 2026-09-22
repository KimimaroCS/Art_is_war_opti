"""Interface commune des backends de saturation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..monitors import Monitor


@dataclass(frozen=True)
class BackendInfo:
    name: str
    exclusive_fullscreen: bool
    detail: str


class SaturationBackend(ABC):
    @abstractmethod
    def info(self) -> BackendInfo:
        raise NotImplementedError

    @abstractmethod
    def apply(self, saturation: float, monitor: Monitor | None, all_monitors: bool) -> None:
        """saturation: 0.0 min → 1.0 normal → 2.0 max."""
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError
