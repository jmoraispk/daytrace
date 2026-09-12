from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfoNotFoundError

import pytest

from daytrace import cli
from daytrace.providers import SummaryProviderError
from daytrace.source import ActivityWatchConnectionError


def test_module_help_is_available() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "daytrace", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "activitywatch" in result.stdout
    assert result.stderr == ""


def test_cli_writes_utf8_lf_output_file(
    monkeypatch, tmp_path: Path, make_bundle
) -> None:
    monkeypatch.setattr(cli, "collect_day", lambda *args, **kwargs: make_bundle())
    output = tmp_path / "summary.md"

    status = cli.main(
        ["activitywatch", "--date", "2026-09-10", "--output", str(output)]
    )

    assert status == 0
    assert output.read_bytes().startswith("# DayTrace — 2026-09-10\n".encode())
    assert b"\r" not in output.read_bytes()


def test_cli_keeps_operational_error_out_of_stdout(monkeypatch, capsys) -> None:
    def fail(*args, **kwargs):
        raise ActivityWatchConnectionError("ActivityWatch info request failed")

    monkeypatch.setattr(cli, "collect_day", fail)
    status = cli.main(["activitywatch", "--date", "2026-09-10"])

    captured = capsys.readouterr()
    assert status == 1
    assert captured.out == ""
    assert captured.err == (
        "error: ActivityWatch is not reachable at http://127.0.0.1:5600; "
        "start ActivityWatch or pass --server\n"
    )


def test_cli_reports_invalid_timezone_separately(monkeypatch, capsys) -> None:
    def fail(*args, **kwargs):
        raise ZoneInfoNotFoundError("No time zone found with key Invalid/Zone")

    monkeypatch.setattr(cli, "collect_day", fail)
    status = cli.main(
        ["activitywatch", "--date", "2026-09-10", "--timezone", "Invalid/Zone"]
    )

    captured = capsys.readouterr()
    assert status == 1
    assert captured.out == ""
    assert captured.err == "error: invalid timezone 'Invalid/Zone'\n"


def test_cli_reports_invalid_server_url_without_echoing_it(monkeypatch, capsys) -> None:
    def fail(*args, **kwargs):
        raise ValueError("invalid ActivityWatch server URL")

    monkeypatch.setattr(cli, "collect_day", fail)
    status = cli.main(
        [
            "activitywatch",
            "--date",
            "2026-09-10",
            "--server",
            "http://user:secret@host",
        ]
    )

    captured = capsys.readouterr()
    assert status == 1
    assert captured.out == ""
    assert captured.err == "error: invalid ActivityWatch server URL\n"
    assert "secret" not in captured.err


def test_atomic_output_failure_preserves_original(
    monkeypatch, capsys, tmp_path: Path, make_bundle
) -> None:
    monkeypatch.setattr(cli, "collect_day", lambda *args, **kwargs: make_bundle())
    output = tmp_path / "summary.md"
    output.write_bytes(b"original\n")

    def fail_replace(source, destination):
        raise OSError("private operating-system detail")

    monkeypatch.setattr(cli.os, "replace", fail_replace)
    status = cli.main(
        ["activitywatch", "--date", "2026-09-10", "--output", str(output)]
    )

    captured = capsys.readouterr()
    assert status == 1
    assert captured.out == ""
    assert captured.err == f"error: could not write output file {str(output)!r}\n"
    assert "private operating-system detail" not in captured.err
    assert output.read_bytes() == b"original\n"
    assert list(tmp_path.glob(".summary.md.*.tmp")) == []


def test_ai_requires_explicit_provider_and_model(capsys) -> None:
    status = cli.main(["activitywatch", "--date", "2026-09-10", "--summary", "ai"])
    captured = capsys.readouterr()
    assert status == 1
    assert captured.out == ""
    assert "--provider openai and --model are required" in captured.err


def test_cloud_disclosure_precedes_hidden_key_and_provider_call(
    monkeypatch, capsys, make_bundle, make_digest, make_provenance
) -> None:
    calls = []
    monkeypatch.setattr(cli, "collect_day", lambda *a, **k: make_bundle())
    monkeypatch.setattr(
        cli, "input", lambda prompt: calls.append(("confirm", prompt)) or "y"
    )
    monkeypatch.setattr(
        cli.getpass,
        "getpass",
        lambda prompt: calls.append(("key", prompt)) or "secret",
    )
    monkeypatch.setattr(
        cli,
        "_openai_summary",
        lambda *a, **k: (
            calls.append(("provider", "called"))
            or (make_digest(), make_provenance())
        ),
    )

    status = cli.main(
        [
            "activitywatch",
            "--date",
            "2026-09-10",
            "--summary",
            "ai",
            "--provider",
            "openai",
            "--model",
            "user-model",
        ]
    )

    captured = capsys.readouterr()
    assert status == 0
    assert [item[0] for item in calls] == ["confirm", "key", "provider"]
    assert "openai" in captured.err
    assert "1 compact episode" in captured.err
    assert "secret" not in captured.out + captured.err


def test_ai_failure_writes_deterministic_fallback_and_returns_two(
    monkeypatch, capsys, make_bundle
) -> None:
    monkeypatch.setattr(cli, "collect_day", lambda *a, **k: make_bundle())
    monkeypatch.setattr(
        cli,
        "_openai_summary",
        lambda *a, **k: (_ for _ in ()).throw(
            SummaryProviderError("OpenAI summary request failed")
        ),
    )
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "secret")

    status = cli.main(
        [
            "activitywatch",
            "--date",
            "2026-09-10",
            "--summary",
            "ai",
            "--provider",
            "openai",
            "--model",
            "user-model",
            "--yes",
        ]
    )

    captured = capsys.readouterr()
    assert status == 2
    assert "Summary: Deterministic activity episodes" in captured.out
    assert "AI summary unavailable" in captured.err


def test_raw_and_details_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(
            [
                "activitywatch",
                "--date",
                "2026-09-10",
                "--raw",
                "--details",
            ]
        )
    assert exc.value.code == 2


def test_json_format_produces_json_only_stdout(
    monkeypatch, capsys, make_bundle
) -> None:
    monkeypatch.setattr(cli, "collect_day", lambda *a, **k: make_bundle())

    status = cli.main(
        [
            "activitywatch",
            "--date",
            "2026-09-10",
            "--format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert status == 0
    assert json.loads(captured.out)["schema"] == "daytrace.episode-bundle.v1"
    assert captured.err == ""
