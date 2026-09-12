from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class SourceKind(StrEnum):
    WINDOW = "current-window"
    AFK = "afk"
    EDITOR = "editor"
    BROWSER = "browser"


class DiagnosticCode(StrEnum):
    NON_POSITIVE_EVENT = "non-positive-event"
    NAIVE_TIMESTAMP = "naive-timestamp"
    UNSUPPORTED_BUCKET = "unsupported-bucket"
    WINDOW_CONFLICT = "window-conflict"
    SANITIZED_FIELD = "sanitized-field"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class OutcomeStrength(StrEnum):
    OBSERVED = "observed"
    LIKELY = "likely"
    NONE = "none"


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
class DiagnosticCount:
    code: DiagnosticCode
    count: int


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
    url_path: str | None = None
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
            self.url_path,
            self.language,
            self.status,
        )


@dataclass(frozen=True, slots=True)
class SanitizedObservation:
    evidence_id: str
    kind: SourceKind
    start: datetime
    end: datetime
    app: str | None = None
    title: str | None = None
    project: str | None = None
    file: str | None = None
    url_host: str | None = None
    url_path: str | None = None
    language: str | None = None

    @property
    def duration_seconds(self) -> float:
        return (self.end - self.start).total_seconds()


@dataclass(frozen=True, slots=True)
class ContextSignal:
    kind: SourceKind
    evidence_id: str
    title: str | None = None
    project: str | None = None
    file: str | None = None
    url_host: str | None = None
    url_path: str | None = None
    language: str | None = None


@dataclass(frozen=True, slots=True)
class ActivitySlice:
    start: datetime
    end: datetime
    focused: bool
    app: str | None
    title: str | None
    contexts: tuple[ContextSignal, ...]
    evidence_ids: tuple[str, ...]

    @property
    def duration_seconds(self) -> float:
        return (self.end - self.start).total_seconds()


@dataclass(frozen=True, slots=True)
class OutcomeSignal:
    code: str
    label: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ActivitySession:
    session_id: str
    start: datetime
    end: datetime
    active_seconds: float
    focused_seconds: float | None
    label: str
    slices: tuple[ActivitySlice, ...]
    evidence_ids: tuple[str, ...]
    outcome_signals: tuple[OutcomeSignal, ...]


@dataclass(frozen=True, slots=True)
class SessionBundle:
    day: date
    timezone_name: str
    focused_seconds: float | None
    sessions: tuple[ActivitySession, ...]
    diagnostics: tuple[DiagnosticCount, ...]


@dataclass(frozen=True, slots=True)
class ActivityAnchor:
    kind: str
    value: str


@dataclass(frozen=True, slots=True)
class ActivityLabelCount:
    value: str
    count: int


@dataclass(frozen=True, slots=True)
class ActivityEpisode:
    episode_id: str
    start: datetime
    end: datetime
    active_seconds: float
    focused_seconds: float | None
    label: str
    session_ids: tuple[str, ...]
    anchors: tuple[ActivityAnchor, ...]
    applications: tuple[ActivityLabelCount, ...]
    activity_labels: tuple[ActivityLabelCount, ...]
    outcome_signals: tuple[OutcomeSignal, ...]
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EpisodeBundle:
    day: date
    timezone_name: str
    focused_seconds: float | None
    episodes: tuple[ActivityEpisode, ...]
    sessions: tuple[ActivitySession, ...]
    diagnostics: tuple[DiagnosticCount, ...]


@dataclass(frozen=True, slots=True)
class TopicSummary:
    text: str
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OutcomeSummary:
    text: str
    strength: OutcomeStrength
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkstreamSummary:
    label: str
    confidence: Confidence
    session_ids: tuple[str, ...]
    topics: tuple[TopicSummary, ...]
    outcomes: tuple[OutcomeSummary, ...]


@dataclass(frozen=True, slots=True)
class WorkstreamDigest:
    workstreams: tuple[WorkstreamSummary, ...]
    unassigned_session_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SummaryRequest:
    schema: str
    payload: Mapping[str, object]
    character_count: int
    session_count: int
    data_categories: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    payload: Mapping[str, object]
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class SummaryProvenance:
    provider: str
    model: str
    prompt_schema: str
    input_tokens: int | None
    output_tokens: int | None


@dataclass(frozen=True, slots=True)
class ApplicationTotal:
    app: str
    seconds: float


@dataclass(frozen=True, slots=True)
class ActivityReport:
    day: date
    timezone_name: str
    project: str | None
    active_seconds: float | None
    sources: tuple[SourceKind, ...]
    timeline: tuple[ActivityRecord, ...]
    applications: tuple[ApplicationTotal, ...]
