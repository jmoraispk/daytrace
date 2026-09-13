from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

from daytrace.activitywatch import collect_day
from daytrace.json_output import render_digest_json, render_episode_json
from daytrace.markdown import render_digest_markdown, render_episode_markdown
from daytrace.models import (
    Confidence,
    OutcomeStrength,
    RawBucket,
    RawEvent,
    ServerInfo,
    SummaryProvenance,
)
from daytrace.summarize import build_summary_plan, validate_digest
from daytrace.time import resolve_day


FIXTURES = Path(__file__).parent / "fixtures" / "cross-language"


class FixtureSource:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def get_info(self) -> ServerInfo:
        return ServerInfo("v0.synthetic", True)

    def list_buckets(self) -> tuple[RawBucket, ...]:
        return tuple(RawBucket(**item) for item in self.payload["buckets"])

    def get_events(self, bucket_id, start, end) -> tuple[RawEvent, ...]:
        events = self.payload["events"].get(bucket_id, [])
        return tuple(
            RawEvent(
                id=item["id"],
                timestamp=datetime.fromisoformat(item["timestamp"]),
                duration_seconds=float(item["duration"]),
                data=item["data"],
            )
            for item in events
        )


def build_reference_outputs() -> dict[str, str]:
    pipeline_input = json.loads((FIXTURES / "pipeline-input.json").read_text())
    bundle = collect_day(
        date.fromisoformat(pipeline_input["day"]),
        timezone_name=pipeline_input["timezone"],
        source=FixtureSource(pipeline_input),
    )
    plan = build_summary_plan(bundle)
    episode_payload = json.loads(render_episode_json(bundle, details=True, raw=True))
    episode_payload["summary_plan"] = {
        "episode_count": plan.episode_count,
        "input_character_count": plan.input_character_count,
        "planned_request_count": plan.planned_request_count,
        "data_categories": list(plan.data_categories),
        "request_episode_ids": [list(item.episode_ids) for item in plan.requests],
    }

    digest_input = json.loads((FIXTURES / "digest-input.json").read_text())
    digest = validate_digest(
        digest_input["payload"], {item.episode_id for item in bundle.episodes}
    )
    raw_provenance = digest_input["provenance"]
    provenance = SummaryProvenance(
        provider=raw_provenance["provider"],
        model=raw_provenance["model"],
        prompt_schema=raw_provenance["prompt_schema"],
        input_tokens=raw_provenance["input_tokens"],
        output_tokens=raw_provenance["output_tokens"],
        request_count=raw_provenance["request_count"],
    )
    dst = {}
    for value in ("2026-03-08", "2026-11-01"):
        window = resolve_day(date.fromisoformat(value), "America/Los_Angeles")
        def utc_iso(item: datetime) -> str:
            return item.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        dst[value] = {
            "timezone": window.timezone_name,
            "start": utc_iso(window.start),
            "end": utc_iso(window.end),
            "duration_seconds": (window.end.timestamp() - window.start.timestamp()),
        }

    return {
        "pipeline-expected.json": json.dumps(episode_payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        "episode-expected.md": render_episode_markdown(bundle, details=True, raw=True),
        "digest-expected.json": render_digest_json(bundle, digest, provenance, details=True),
        "digest-expected.md": render_digest_markdown(bundle, digest, provenance, details=True),
        "dst-expected.json": json.dumps(dst, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    outputs = build_reference_outputs()
    if args.write:
        for name, content in outputs.items():
            (FIXTURES / name).write_text(content)
    else:
        print(json.dumps(outputs, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
