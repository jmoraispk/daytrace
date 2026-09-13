from __future__ import annotations

import io
import json
import subprocess
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfoNotFoundError

import pytest

from daytrace import __version__, cli
from daytrace.models import ProviderFailureKind, SummaryFailureContext, SummaryPass
from daytrace.providers import SummaryProviderError
from daytrace.source import ActivityWatchConnectionError
from daytrace.summarize import (
    EpisodeRequestTooLarge,
    MergeRequestTooLarge,
    SummaryValidationError,
)


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
    monkeypatch,
    capsys,
    make_episode_bundle,
    make_summary_plan,
    make_digest,
    make_provenance,
) -> None:
    calls = []
    plan = make_summary_plan(chunk_count=3, episode_count=437)
    monkeypatch.setattr(cli, "collect_day", lambda *a, **k: make_episode_bundle())
    monkeypatch.setattr(cli, "build_summary_plan", lambda bundle: plan)
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
        lambda bundle, key, model, resolved_plan: (
            calls.append(("summary", model))
            or (make_digest(), make_provenance(4))
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
    assert [item[0] for item in calls] == ["confirm", "key", "summary"]
    assert "openai" in captured.err
    assert "437 compact episodes" in captured.err
    assert "3 summary chunks plus 1 merge call" in captured.err
    assert "one automatic allocation-repair retry" in captured.err
    assert "total initial input" in captured.err
    assert "AI summary complete; writing output..." in captured.err
    assert "secret" not in captured.out + captured.err


def test_cloud_confirmation_defaults_to_yes_on_enter(
    monkeypatch, capsys, make_summary_plan
) -> None:
    prompts = []
    monkeypatch.setattr(
        cli, "input", lambda prompt: prompts.append(prompt) or ""
    )

    confirmed = cli._confirm_cloud_send(
        make_summary_plan(), "openai", "model", assume_yes=False
    )

    assert confirmed is True
    assert prompts == ["Continue? [Y/n] "]
    assert "About to send" in capsys.readouterr().err


def test_cloud_confirmation_does_not_accept_unrecognized_input(
    monkeypatch, make_summary_plan
) -> None:
    monkeypatch.setattr(cli, "input", lambda prompt: "maybe")

    confirmed = cli._confirm_cloud_send(
        make_summary_plan(), "openai", "model", assume_yes=False
    )

    assert confirmed is False


def test_progress_provider_reports_waiting_and_received(
    monkeypatch, capsys, make_summary_plan
) -> None:
    response = object()

    class Provider:
        def summarize(self, request):
            return response

        def merge(self, request):
            return response

    clock = iter((10.0, 22.4, 30.0, 35.2))
    monkeypatch.setattr(cli.time, "monotonic", lambda: next(clock))
    plan = make_summary_plan(chunk_count=2)
    provider = cli._ProgressProvider(Provider(), summary_chunks=2)

    assert provider.summarize(plan.requests[0]) is response
    assert provider.merge(object()) is response

    assert capsys.readouterr().err == (
        "AI summary: chunk 1/2 — waiting for OpenAI...\n"
        "AI summary: chunk 1/2 — response received after 12s; validating...\n"
        "AI summary: merge — waiting for OpenAI...\n"
        "AI summary: merge — response received after 5s; validating...\n"
    )


def test_progress_provider_counts_elapsed_seconds_while_waiting(
    monkeypatch, make_summary_plan
) -> None:
    class InteractiveBuffer(io.StringIO):
        def isatty(self) -> bool:
            return True

    class SlowProvider:
        def summarize(self, request):
            time.sleep(1.1)
            return object()

        def merge(self, request):
            raise AssertionError("merge must not be called")

    stream = InteractiveBuffer()
    monkeypatch.setattr(cli.sys, "stderr", stream)
    plan = make_summary_plan()

    cli._ProgressProvider(SlowProvider(), summary_chunks=1).summarize(
        plan.requests[0]
    )

    progress = stream.getvalue()
    assert "\rAI summary: chunk 1/1 — waiting for OpenAI... 1s" in progress
    assert "response received after 1s; validating..." in progress


def test_progress_provider_ends_live_line_when_request_fails(
    monkeypatch, make_summary_plan
) -> None:
    class InteractiveBuffer(io.StringIO):
        def isatty(self) -> bool:
            return True

    class FailingProvider:
        def summarize(self, request):
            raise RuntimeError("provider failed")

        def merge(self, request):
            raise AssertionError("merge must not be called")

    stream = InteractiveBuffer()
    monkeypatch.setattr(cli.sys, "stderr", stream)
    plan = make_summary_plan()

    with pytest.raises(RuntimeError, match="provider failed"):
        cli._ProgressProvider(FailingProvider(), summary_chunks=1).summarize(
            plan.requests[0]
        )

    assert stream.getvalue().endswith("request ended after 0s.\n")


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (EpisodeRequestTooLarge(), "one compact episode exceeds"),
        (MergeRequestTooLarge(), "compact merge request exceeds"),
        (
            SummaryProviderError(ProviderFailureKind.AUTHENTICATION),
            "authentication, access, or billing",
        ),
        (SummaryProviderError(ProviderFailureKind.RATE_LIMIT), "rate limit or quota"),
        (SummaryProviderError(ProviderFailureKind.NETWORK), "network"),
        (SummaryProviderError(ProviderFailureKind.SERVICE), "service unavailable"),
        (SummaryValidationError("invalid"), "invalid structured response"),
    ],
)
def test_ai_failure_is_specific_content_free_and_falls_back(
    failure,
    message,
    monkeypatch,
    capsys,
    make_episode_bundle,
    make_summary_plan,
) -> None:
    monkeypatch.setattr(cli, "collect_day", lambda *a, **k: make_episode_bundle())
    monkeypatch.setattr(
        cli, "build_summary_plan", lambda bundle: make_summary_plan()
    )
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "runtime-secret")
    monkeypatch.setattr(
        cli,
        "_openai_summary",
        lambda bundle, key, model, plan: (_ for _ in ()).throw(failure),
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
            "model",
            "--yes",
        ]
    )
    captured = capsys.readouterr()

    assert status == 2
    assert message in captured.err
    assert "runtime-secret" not in captured.out + captured.err
    assert "Summary: Deterministic activity episodes" in captured.out


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


def test_debug_output_requires_ai_mode(tmp_path: Path) -> None:
    args = cli.build_parser().parse_args(
        [
            "activitywatch",
            "--date",
            "2026-09-10",
            "--debug-output",
            str(tmp_path / "debug.json"),
        ]
    )

    assert cli._validate_mode(args) == "--debug-output requires --summary ai"


def test_debug_output_must_differ_from_primary_output(tmp_path: Path) -> None:
    output = tmp_path / "same.json"
    args = cli.build_parser().parse_args(
        [
            "activitywatch",
            "--date",
            "2026-09-10",
            "--summary",
            "ai",
            "--provider",
            "openai",
            "--model",
            "model",
            "--output",
            str(output),
            "--debug-output",
            str(output),
        ]
    )

    assert cli._validate_mode(args) == "--debug-output must differ from --output"


def test_validation_failure_writes_private_fallback_and_safe_debug_json(
    monkeypatch, capsys, tmp_path: Path, make_episode_bundle
) -> None:
    output = tmp_path / "daytrace.md"
    debug = tmp_path / "failure.json"
    private = "private generated label"
    context = SummaryFailureContext(
        provider="openai",
        model="model",
        stage=SummaryPass.CHUNK,
        call_index=1,
        request_character_count=1234,
        item_ids=("episode-001",),
        response_id="resp_test",
        request_id="req_test",
    )
    failure = SummaryValidationError(
        "empty-ids",
        "workstreams[0].episode_ids",
        context,
        {
            "workstream_count": 1,
            "known_allocated_ids": [],
            "unknown_id_count": 0,
        },
    )
    monkeypatch.setattr(cli, "collect_day", lambda *a, **k: make_episode_bundle())
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "runtime-secret")
    monkeypatch.setattr(
        cli,
        "_openai_summary",
        lambda *a, **k: (_ for _ in ()).throw(failure),
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
            "model",
            "--yes",
            "--output",
            str(output),
            "--debug-output",
            str(debug),
        ]
    )
    captured = capsys.readouterr()
    report = json.loads(debug.read_text(encoding="utf-8"))

    assert status == 2
    assert "Summary: Deterministic activity episodes" in output.read_text()
    assert report["schema"] == "daytrace.ai-failure.v1"
    assert report["validation"] == {
        "code": "empty-ids",
        "field": "workstreams[0].episode_ids",
    }
    assert f"daytrace {__version__}" in captured.err
    assert "code=empty-ids" in captured.err
    assert "field=workstreams[0].episode_ids" in captured.err
    assert (
        "AI failure metadata will be written locally if this run fails."
        in captured.err
    )
    combined = captured.out + captured.err + debug.read_text(encoding="utf-8")
    assert private not in combined
    assert "runtime-secret" not in combined


def test_debug_output_failure_preserves_existing_file(
    monkeypatch, capsys, tmp_path: Path, make_episode_bundle
) -> None:
    debug = tmp_path / "failure.json"
    debug.write_text("original\n", encoding="utf-8")
    monkeypatch.setattr(cli, "collect_day", lambda *a, **k: make_episode_bundle())
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "runtime-secret")
    monkeypatch.setattr(
        cli,
        "_openai_summary",
        lambda *a, **k: (_ for _ in ()).throw(SummaryProviderError()),
    )
    monkeypatch.setattr(
        cli.os,
        "replace",
        lambda *a, **k: (_ for _ in ()).throw(OSError()),
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
            "model",
            "--yes",
            "--debug-output",
            str(debug),
        ]
    )
    captured = capsys.readouterr()

    assert status == 1
    assert debug.read_text(encoding="utf-8") == "original\n"
    assert "could not write AI failure metadata" in captured.err
    assert str(debug) not in captured.err
    assert "runtime-secret" not in captured.err


def test_validation_warning_redacts_untrusted_metadata() -> None:
    private = "private generated value"
    context = SummaryFailureContext(
        provider="openai",
        model="model",
        stage=SummaryPass.CHUNK,
        call_index=1,
        request_character_count=1234,
        item_ids=("episode-001",),
        response_id=f"resp\\n{private}",
        request_id=f"req\\n{private}",
    )
    failure = SummaryValidationError(
        f"invalid\\n{private}",
        f"field\\n{private}",
        context,
    )

    message = cli._summary_failure_message(failure, "openai", "model")

    assert private not in message
    assert "code=redacted-code" in message
    assert "field=redacted-field" in message
    assert "response_id=[redacted-response]" in message
    assert "request_id=[redacted-request]" in message
