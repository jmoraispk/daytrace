from __future__ import annotations

import re
from pathlib import PurePath, PureWindowsPath
from urllib.parse import urlsplit

from daytrace.sanitize import sanitize_generated_text


URL_TOKEN = re.compile(
    r"(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,}"
    r"(?:/[^\s?#]*)?(?:\?[^\s#]*)?(?:#[^\s]*)?",
    re.I,
)
DIRECT_MESSAGE = re.compile(r"^.*?\s*\(DM\).*?(Slack|Teams).*$", re.I)


def _host_only(match: re.Match[str]) -> str:
    try:
        raw = match.group(0)
        parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
        return (parsed.hostname or "[redacted-url]").casefold()
    except ValueError:
        return "[redacted-url]"


def minimize_cloud_text(value: str | None) -> str | None:
    if not value:
        return None
    replaced = URL_TOKEN.sub(_host_only, value)
    cleaned = sanitize_generated_text(replaced)
    return cleaned[:500] or None


def minimize_cloud_title(app: str | None, title: str | None) -> str | None:
    if not title:
        return None
    surface = app or ""
    dm = DIRECT_MESSAGE.match(title)
    if dm:
        return f"Direct message - {dm.group(1).title()}"
    folded_app = surface.casefold()
    folded_title = title.casefold()
    if "teams" in folded_app or "microsoft teams" in folded_title:
        return "Meeting - Microsoft Teams"
    communication_text = f"{folded_app} {folded_title}"
    if any(item in communication_text for item in ("outlook", "gmail")) or any(
        item in folded_app for item in ("mail", "thunderbird")
    ):
        category = "Inbox" if "inbox" in folded_title else (
            "Calendar" if "calendar" in folded_title else "Email"
        )
        display = "Outlook" if "outlook" in communication_text else (
            "Gmail" if "gmail" in communication_text else "Mail"
        )
        return f"{category} - {display}"
    return minimize_cloud_text(title)


def minimize_cloud_path(value: str | None) -> str | None:
    if not value:
        return None
    path = PureWindowsPath(value) if "\\" in value or ":" in value else PurePath(value)
    return minimize_cloud_text(path.name or None)
