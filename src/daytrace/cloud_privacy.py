from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import PurePath, PureWindowsPath

from daytrace.sanitize import sanitize_generated_text
DIRECT_MESSAGE = re.compile(r"^.*?\s*\(DM\).*?(Slack|Teams).*$", re.I)


class CloudPrivacyError(RuntimeError):
    """A content-free provider-egress privacy failure."""

    def __init__(self) -> None:
        super().__init__("unsafe-cloud-payload")


def assert_cloud_safe_payload(value: object) -> None:
    if isinstance(value, str):
        if sanitize_generated_text(value) != value:
            raise CloudPrivacyError()
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            assert_cloud_safe_payload(key)
            assert_cloud_safe_payload(item)
        return
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        for item in value:
            assert_cloud_safe_payload(item)

def minimize_cloud_text(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = sanitize_generated_text(value)
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
