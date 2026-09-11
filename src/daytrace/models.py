from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class SourceKind(StrEnum):
    WINDOW = "current-window"
    AFK = "afk"
    EDITOR = "editor"
    BROWSER = "browser"


@dataclass(frozen=True, slots=True)
class ServerEndpoint:
    protocol: str
    host: str
    port: int


@dataclass(frozen=True, slots=True)
class ServerInfo:
    version: str
    testing: bool


@dataclass(frozen=True, slots=True)
class DayWindow:
    timezone_name: str
    start: datetime
    end: datetime


@dataclass(frozen=True, slots=True)
class RawBucket:
    id: str
    type: str
    client: str
    hostname: str


@dataclass(frozen=True, slots=True)
class RawEvent:
    id: str
    timestamp: datetime
    duration_seconds: float
    data: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", MappingProxyType(dict(self.data)))


@dataclass(frozen=True, slots=True)
class ActivityRecord:
    event_id: str
    bucket_id: str
    kind: SourceKind
    start: datetime
    end: datetime
    app: str | None = None
    title: str | None = None
    project: str | None = None
    file: str | None = None
    url_host: str | None = None
    language: str | None = None
    status: str | None = None

    @property
    def duration_seconds(self) -> float:
        return (self.end - self.start).total_seconds()

    def content_key(self) -> tuple[object, ...]:
        return (
            self.bucket_id,
            self.kind,
            self.app,
            self.title,
            self.project,
            self.file,
            self.url_host,
            self.language,
            self.status,
        )
