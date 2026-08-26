# Product and UX specification

## Product promise

“A searchable, editable text trace of your day—processed locally, with every
source under your control.”

The interface should feel like a calm system utility, not a surveillance
dashboard. Use native system typography, compact spacing, strong contrast, one
accent color, and plain-language states. Avoid gamification, productivity
scores, dark patterns, or an always-busy animation.

## Primary jobs

1. Start a trustworthy trace with only the sources I choose.
2. See at a glance whether Daytrace is active, paused, blocked, or unhealthy.
3. Reconstruct a time period from concise text and source provenance.
4. Find an activity by words, app, date, week, or time of day.
5. Review and edit a summary before it is exported or shared.
6. Exclude sensitive apps/times and delete data with confidence.

## Navigation

Keep the main window to five destinations:

- **Today:** current status, timeline, gaps, and end-of-day summary.
- **Search:** query plus calendar/app/source filters and evidence preview.
- **Calendar:** year → ISO week → day → day part navigation.
- **Exports:** local exports, GitHub connection, queue, and last verified sync.
- **Settings:** collection, privacy, models, storage, appearance, and diagnostics.

The tray menu is the daily control surface:

```text
Daytrace — Tracing
Screen text · Microphone · Window context
────────────────────────────
Pause 15 minutes
Pause until tomorrow
Private mode…
Open Today
────────────────────────────
Settings
Quit Daytrace
```

The first line is never ambiguous. Use “Paused,” “Permission needed,” “Storage
error,” or “Tracing” rather than a generic colored dot.

## Onboarding

1. **Promise:** local text journal, no media archive, no account required.
2. **Choose sources:** four independent cards—screen text, microphone,
   keyboard activity, and window context—all initially off.
3. **Request permissions:** one OS prompt at a time, only after the person clicks
   enable. Explain how to repair a denial.
4. **Choose cadence:** Balanced is recommended; show the expected behavior,
   battery impact, and schedule. Audio has meeting/speech options rather than a
   misleading minute interval.
5. **Choose processing:** deterministic/local, installed local model, or BYOK.
   Cloud choices show exactly what leaves the device.
6. **Privacy rules:** suggest password managers, banking, health, private
   browsing, and custom app/window exclusions.
7. **Test trace:** create a synthetic preview first, then let the user run a
   clearly labeled 60-second real test and inspect/delete the resulting text.

Onboarding is complete even if every optional source remains off; Daytrace can
still be configured before collection.

## Today screen

Header:

- truthful state (“Tracing since 8:42 AM”);
- a single Pause/Resume action;
- next summary time;
- source health revealed on click, not four dashboard cards.

Timeline rows show time range, app, one or two lines of text, and small source
labels. Repeated observations merge into a duration. Gaps are explicit (“No
data—computer idle” or “Microphone processing fell behind”), never interpolated.
Selecting a row opens a detail drawer with full extracted text, provenance,
confidence, policy, edit, exclude similar, and delete.

The end-of-day summary appears as an editable outline:

```text
Wednesday, August 26

09:00–10:15  Planned Daytrace architecture
  • Compared accessibility-first extraction with OCR fallback.
  • Decided on SQLite + FTS5 for local search.

10:30–11:05  Design review
  • Refined consent and pause flows.
```

Every bullet can reveal its supporting timeline entries. User edits are marked
as user-authored and are not overwritten on regeneration without confirmation.

## Collection settings

Present each source as a row with state, schedule, and scope:

- Screen text: enabled, Balanced, focused window, accessibility + OCR fallback.
- Microphone: disabled, speech only, selected input device.
- Keyboard activity: enabled, counts/shortcuts only, no typed content.
- Window context: enabled, app + redacted title.
- Browser context: extension not installed, title + origin-only when enabled.

Global controls include working hours, idle cutoff, battery/thermal policy,
private-mode shortcut, excluded apps/windows/sites, retention, and “delete all
data.” Source-specific controls stay inside the relevant row.

## Search behavior

The search field supports ordinary words and visible filter controls; do not
require users to learn FTS syntax. Results group by day and segment, highlight
matches, and retain exact time/app/source context. Calendar filters use local
capture dates. Offer exact phrase, app, source, and date range as structured
filters; compile them to parameterized SQL and escaped FTS queries.

No model is required for search. A later natural-language query feature must
show the generated filters and cannot run arbitrary SQL.

## Privacy interactions

- **Private mode:** pauses all sources immediately for a chosen duration or
  until resumed. Tray/window title clearly show it. No reason is required.
- **Exclude similar:** proposes a precise app, window pattern, or site rule and
  previews affected future capture; it does not retroactively delete without a
  separate choice.
- **Delete:** entry and day deletion are immediate locally with a short undo
  window implemented as an in-database tombstone, not a hidden copy. Synced
  deletion limitations are explained.
- **Provider disclosure:** before first cloud use, show selected time range,
  character count, provider/model, estimated cost, and retention link.
- **Permission lost:** stop that source, keep others running, and show a repair
  action. Never repeatedly trigger an OS permission prompt.

## Visual language

- 8 px spacing grid; 12 px compact and 16 px standard padding.
- 14–15 px body text, 12–13 px metadata, 24–28 px page title.
- Neutral slate surfaces with one teal/blue accent. Amber is degraded/attention;
  red is stopped/error/destructive, not normal recording decoration.
- 8–12 px corner radii, hairline borders, very light shadows only for drawers.
- Respect system light/dark mode and reduced motion. Never encode state by color
  alone.
- Minimum 44×44 px pointer targets around destructive or frequent actions;
  full keyboard navigation, visible focus, semantic headings, screen-reader
  announcements for state changes, and WCAG 2.2 AA contrast.

## Key copy

- “Screen text” instead of “record screen” when the durable output is OCR or
  accessibility text.
- “Microphone transcript” instead of “audio history.”
- “Keyboard activity (no typed text)” for v1.
- “Send selected text to [provider]” rather than “Enable AI.”
- “Delete from this device” and “Request deletion in synced exports” as separate
  outcomes.
- “Daytrace does not intentionally save screenshots or audio” rather than an
  absolute erasure promise the OS cannot guarantee.

## Empty and failure states

- Empty today: show current source state and one clear next action, not sample
  data that could be mistaken for a real trace.
- Unsupported capability: identify the OS/desktop limitation and link to a
  technical explanation.
- Processing backlog: show delay and dropped/gap events; allow lower-cost mode.
- Database error: pause capture before risking loss, preserve the file, offer a
  verified backup/repair path, and never auto-reset.
- Provider error: keep local journal working and offer deterministic summary.
