from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlsplit

from aw_client import ActivityWatchClient

from daytrace.models import RawBucket, RawEvent, ServerEndpoint, ServerInfo


class ActivityWatchConnectionError(RuntimeError):
    """A privacy-safe failure while reading ActivityWatch."""


class ActivitySource(Protocol):
    def get_info(self) -> ServerInfo: ...

    def list_buckets(self) -> tuple[RawBucket, ...]: ...

    def get_events(
        self, bucket_id: str, start: datetime, end: datetime
    ) -> tuple[RawEvent, ...]: ...


def parse_server_url(url: str) -> ServerEndpoint:
    parsed = urlsplit(url)
    valid = (
        parsed.scheme in {"http", "https"}
        and parsed.hostname is not None
        and parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    )
    if not valid:
        raise ValueError("invalid ActivityWatch server URL")
    try:
        port = parsed.port or 5600
    except ValueError as exc:
        raise ValueError("invalid ActivityWatch server URL") from exc
    return ServerEndpoint(parsed.scheme, parsed.hostname, port)


class AwClientSource:
    def __init__(self, client: ActivityWatchClient | Any) -> None:
        self._client = client

    @classmethod
    def from_url(cls, url: str) -> AwClientSource:
        endpoint = parse_server_url(url)
        client = ActivityWatchClient(
            "daytrace",
            host=endpoint.host,
            port=endpoint.port,
            protocol=endpoint.protocol,
        )
        return cls(client)

    def get_info(self) -> ServerInfo:
        try:
            info = self._client.get_info()
            return ServerInfo(
                str(info.get("version", "unknown")), bool(info.get("testing"))
            )
        except Exception as exc:
            raise ActivityWatchConnectionError(
                "ActivityWatch info request failed"
            ) from exc

    def list_buckets(self) -> tuple[RawBucket, ...]:
        try:
            buckets = self._client.get_buckets()
            return tuple(
                RawBucket(
                    id=bucket_id,
                    type=str(data.get("type", "")),
                    client=str(data.get("client", "")),
                    hostname=str(data.get("hostname", "")),
                )
                for bucket_id, data in sorted(buckets.items())
            )
        except Exception as exc:
            raise ActivityWatchConnectionError(
                "ActivityWatch bucket request failed"
            ) from exc

    def get_events(
        self, bucket_id: str, start: datetime, end: datetime
    ) -> tuple[RawEvent, ...]:
        try:
            events: Sequence[Any] = self._client.get_events(
                bucket_id, start=start, end=end
            )
            return tuple(
                RawEvent(
                    id=str(event.id),
                    timestamp=event.timestamp,
                    duration_seconds=(
                        event.duration.total_seconds()
                        if isinstance(event.duration, timedelta)
                        else float(event.duration)
                    ),
                    data=event.data,
                )
                for event in events
            )
        except Exception as exc:
            raise ActivityWatchConnectionError(
                f"ActivityWatch event request failed for bucket {bucket_id!r}"
            ) from exc
