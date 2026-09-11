from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from daytrace.models import ServerEndpoint
from daytrace.source import AwClientSource, parse_server_url


def test_parse_server_url_defaults_to_activitywatch_port() -> None:
    assert parse_server_url("http://127.0.0.1") == ServerEndpoint(
        protocol="http", host="127.0.0.1", port=5600
    )


@pytest.mark.parametrize(
    "url",
    [
        "ftp://127.0.0.1:5600",
        "http://user:secret@127.0.0.1:5600",
        "http://127.0.0.1:5600/api",
        "http://127.0.0.1:5600?x=1",
        "http://127.0.0.1:not-a-port",
    ],
)
def test_parse_server_url_rejects_ambiguous_or_secret_urls(url: str) -> None:
    with pytest.raises(ValueError, match="ActivityWatch server URL"):
        parse_server_url(url)


def test_adapter_converts_official_client_objects() -> None:
    event = SimpleNamespace(
        id=7,
        timestamp=datetime(2026, 9, 10, 16, tzinfo=timezone.utc),
        duration=timedelta(minutes=5),
        data={"app": "Code", "title": "daytrace"},
    )
    client = SimpleNamespace(
        get_info=lambda: {"version": "v0.13.2 (rust)", "testing": False},
        get_buckets=lambda: {
            "aw-watcher-window_test": {
                "type": "currentwindow",
                "client": "aw-watcher-window",
                "hostname": "test",
            }
        },
        get_events=lambda bucket_id, **kwargs: [event],
    )
    source = AwClientSource(client)

    assert source.get_info().version == "v0.13.2 (rust)"
    assert source.list_buckets()[0].type == "currentwindow"
    assert (
        source.get_events(
            "aw-watcher-window_test",
            datetime(2026, 9, 10, tzinfo=timezone.utc),
            datetime(2026, 9, 11, tzinfo=timezone.utc),
        )[0].duration_seconds
        == 300
    )
