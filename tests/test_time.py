from datetime import date, timezone

from daytrace.time import resolve_day


def test_resolve_day_builds_half_open_utc_bounds() -> None:
    window = resolve_day(date(2026, 9, 10), "America/Los_Angeles")

    assert window.timezone_name == "America/Los_Angeles"
    assert (
        window.start.astimezone(timezone.utc).isoformat() == "2026-09-10T07:00:00+00:00"
    )
    assert (
        window.end.astimezone(timezone.utc).isoformat() == "2026-09-11T07:00:00+00:00"
    )


def test_resolve_day_preserves_25_hour_dst_day() -> None:
    window = resolve_day(date(2026, 11, 1), "America/Los_Angeles")

    elapsed = window.end.astimezone(timezone.utc) - window.start.astimezone(
        timezone.utc
    )
    assert elapsed.total_seconds() == 25 * 60 * 60


def test_resolve_day_uses_discovered_iana_zone(monkeypatch) -> None:
    monkeypatch.setattr("daytrace.time.get_localzone_name", lambda: "Europe/Lisbon")

    window = resolve_day(date(2026, 9, 10))

    assert window.timezone_name == "Europe/Lisbon"
