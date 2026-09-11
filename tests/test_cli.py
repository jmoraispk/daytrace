from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfoNotFoundError

from daytrace import cli
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


def test_cli_writes_utf8_lf_output_file(monkeypatch, tmp_path: Path) -> None:
    markdown = "# Activity summary — 2026-09-10\r\n"
    monkeypatch.setattr(cli, "summarize_day", lambda *args, **kwargs: markdown)
    output = tmp_path / "summary.md"

    status = cli.main(
        ["activitywatch", "--date", "2026-09-10", "--output", str(output)]
    )

    assert status == 0
    assert output.read_bytes() == "# Activity summary — 2026-09-10\n".encode("utf-8")


def test_cli_keeps_operational_error_out_of_stdout(monkeypatch, capsys) -> None:
    def fail(*args, **kwargs):
        raise ActivityWatchConnectionError("ActivityWatch info request failed")

    monkeypatch.setattr(cli, "summarize_day", fail)
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

    monkeypatch.setattr(cli, "summarize_day", fail)
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

    monkeypatch.setattr(cli, "summarize_day", fail)
    status = cli.main(
        ["activitywatch", "--date", "2026-09-10", "--server", "http://user:secret@host"]
    )

    captured = capsys.readouterr()
    assert status == 1
    assert captured.out == ""
    assert captured.err == "error: invalid ActivityWatch server URL\n"
    assert "secret" not in captured.err


def test_cli_sanitizes_output_write_failure(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli, "summarize_day", lambda *args, **kwargs: "summary\n")

    def fail_write(self, data):
        raise OSError("private operating-system detail")

    monkeypatch.setattr(Path, "write_bytes", fail_write)
    output = tmp_path / "summary.md"
    status = cli.main(
        ["activitywatch", "--date", "2026-09-10", "--output", str(output)]
    )

    captured = capsys.readouterr()
    assert status == 1
    assert captured.out == ""
    assert captured.err == f"error: could not write output file {str(output)!r}\n"
    assert "private operating-system detail" not in captured.err
