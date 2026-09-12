from __future__ import annotations

import html
import re
from zoneinfo import ZoneInfo

from daytrace.diagnostics import diagnostic_messages
from daytrace.models import (
    ActivityRecord,
    ActivityReport,
    ActivitySession,
    ActivitySlice,
    ContextSignal,
    SessionBundle,
    SourceKind,
)


SOURCE_LABEL = {
    SourceKind.WINDOW: "Current window",
    SourceKind.EDITOR: "Editor",
    SourceKind.BROWSER: "Browser",
}


def format_duration(seconds: float) -> str:
    if 0 < seconds < 60:
        return "<1m"
    minutes = max(0, int((seconds + 30) // 60))
    hours, minutes = divmod(minutes, 60)
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


def _single_line(value: str) -> str:
    return " ".join(value.replace("\r", " ").replace("\n", " ").split())


def _escape(value: str) -> str:
    escaped = html.escape(_single_line(value), quote=False).replace("\\", "\\\\")
    return re.sub(r"([`*_{}\[\]#+|])", r"\\\1", escaped)


def _code(value: str) -> str:
    value = _single_line(value)
    longest = max((len(run) for run in re.findall(r"`+", value)), default=0)
    fence = "`" * (longest + 1)
    padding = " " if value.startswith("`") or value.endswith("`") else ""
    return f"{fence}{padding}{value}{padding}{fence}"


def _basename(value: str | None) -> str | None:
    return value.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] if value else None


def _label(record: ActivityRecord) -> str:
    if record.kind is SourceKind.WINDOW:
        values = (record.app, record.title)
    elif record.kind is SourceKind.BROWSER:
        values = (record.url_host, record.title)
    else:
        values = (_basename(record.project), _basename(record.file), record.language)
    label = " — ".join(_escape(value) for value in values if value)
    return label or SOURCE_LABEL[record.kind]


def render_markdown(report: ActivityReport) -> str:
    lines = [f"# Activity summary — {report.day.isoformat()}", ""]
    if report.project is not None:
        lines.append(f"Project filter: {_code(report.project)}")
    lines.extend([f"Timezone: {_code(report.timezone_name)}", "", "## Overview", ""])
    if not report.timeline:
        return "\n".join(lines + ["No matching activity.", ""])

    active = (
        format_duration(report.active_seconds)
        if report.active_seconds is not None
        else "Unavailable"
    )
    lines.extend(
        [
            f"- Active matched time: {active}",
            f"- Timeline entries: {len(report.timeline)}",
            f"- Sources: {', '.join(SOURCE_LABEL[item] for item in report.sources)}",
            "",
            "## Timeline",
            "",
        ]
    )
    zone = ZoneInfo(report.timezone_name)
    for record in report.timeline:
        start = record.start.astimezone(zone).strftime("%H:%M")
        end = record.end.astimezone(zone).strftime("%H:%M")
        lines.append(
            f"- {start}–{end} ({format_duration(record.duration_seconds)}) — {_label(record)}"
        )
    if report.applications:
        lines.extend(["", "## Applications", ""])
        lines.extend(
            f"- {_escape(item.app)} — {format_duration(item.seconds)}"
            for item in report.applications
        )
    return "\n".join(lines) + "\n"


def _session_times(item: ActivitySession | ActivitySlice, zone: ZoneInfo) -> str:
    start = item.start.astimezone(zone).strftime("%H:%M")
    end = item.end.astimezone(zone).strftime("%H:%M")
    return f"{start}–{end}"


def _context_label(context: ContextSignal) -> str:
    values = (
        context.project,
        context.file,
        context.url_host,
        context.url_path,
        context.title,
        context.language,
    )
    return " — ".join(_escape(value) for value in values if value) or context.kind.value


def _append_session_details(
    lines: list[str], item: ActivitySession, zone: ZoneInfo
) -> None:
    if item.evidence_ids:
        lines.append(f"  - Evidence: {', '.join(_code(value) for value in item.evidence_ids)}")
    contexts = {
        (context.kind.value, _context_label(context))
        for activity_slice in item.slices
        for context in activity_slice.contexts
    }
    for kind, label in sorted(contexts):
        lines.append(f"  - {SOURCE_LABEL[SourceKind(kind)]}: {label}")
    if item.focused_seconds is None:
        lines.append("  - Foreground duration: unavailable")
    else:
        lines.append(f"  - Foreground duration: {format_duration(item.focused_seconds)}")


def _append_raw_slices(
    lines: list[str], item: ActivitySession, zone: ZoneInfo
) -> None:
    for activity_slice in item.slices:
        label = activity_slice.title or activity_slice.app or "Context evidence"
        focus = "focused" if activity_slice.focused else "evidence only"
        lines.append(
            f"  - {_session_times(activity_slice, zone)} — {_code(label)} "
            f"({format_duration(activity_slice.duration_seconds)}, {focus})"
        )


def render_session_markdown(
    bundle: SessionBundle, *, details: bool = False, raw: bool = False
) -> str:
    zone = ZoneInfo(bundle.timezone_name)
    focused = (
        format_duration(bundle.focused_seconds)
        if bundle.focused_seconds is not None
        else "Unavailable"
    )
    lines = [
        f"# DayTrace — {bundle.day.isoformat()}",
        "",
        f"Timezone: {_code(bundle.timezone_name)} (inferred at query time)",
        f"Focused activity: {focused}",
        "Summary: Deterministic activity sessions",
        "",
        "## Activity sessions",
        "",
    ]
    if not bundle.sessions:
        lines.append("No activity sessions.")
    for item in sorted(bundle.sessions, key=lambda value: (value.start, value.session_id)):
        lines.append(
            f"- {_session_times(item, zone)} — {_code(item.label)} "
            f"({format_duration(item.active_seconds)})"
        )
        for signal in item.outcome_signals:
            lines.append(f"  - Observed signal: {_escape(signal.label)}")
        if details:
            _append_session_details(lines, item, zone)
        if raw:
            _append_raw_slices(lines, item, zone)

    if bundle.diagnostics:
        lines.extend(["", "## Diagnostics", ""])
        for message in diagnostic_messages(bundle.diagnostics):
            lines.append(f"- {message[0].upper() + message[1:]}.")
    return "\n".join(lines) + "\n"
