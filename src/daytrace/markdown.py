from __future__ import annotations

import html
import re
from zoneinfo import ZoneInfo

from daytrace.models import ActivityRecord, ActivityReport, SourceKind


SOURCE_LABEL = {
    SourceKind.WINDOW: "Current window",
    SourceKind.EDITOR: "Editor",
    SourceKind.BROWSER: "Browser",
}


def format_duration(seconds: float) -> str:
    minutes = max(1, int((seconds + 30) // 60))
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
