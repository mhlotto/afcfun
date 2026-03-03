# Weekly Report Pipeline (Phase 1)

Phase 1 goal: generate a deterministic weekly JSON artifact from DB data and render a readable HTML report from that artifact.

The JSON generator validates output against the `weekly-report.v1` contract before writing.

## Scope lock (Phase 1)

- Source is DB-only (`data/footstat.sqlite3`).
- Inputs are explicit: competition, team list, side filter, season list.
- If `--seasons` is omitted, the latest DB season for the competition is used.
- Artifacts are deterministic for the same input set and report date.

## Artifact contract

Schema version: `weekly-report.v1`

Top-level fields:

- `schema_version`
- `tool_version`
- `generated_at` (UTC ISO timestamp)
- `report_date` (`YYYY-MM-DD`)
- `input`
  - `source` (`db`)
  - `db_path`
  - `competition_code`
  - `teams`
  - `side`
  - `seasons`
  - `metrics`
- `teams`
  - `team`
  - `seasons`
    - `season`
    - `summary`
    - `weekly_rows`
    - `metric_series`
    - `findings`

## Weirdness detectors (Phase 1 + 1.5)

- `referee_fingerprint`
- `discipline_tax`
- `control_without_result`
- `streak_fragility`
- `metric_outlier_zscore`
- `regime_shift`

Each finding includes:

- `kind`
- `season`
- `team`
- `severity`
- `title`
- `summary`
- `evidence`
- `weeks` (optional week references)

## Naming/versioning

Default JSON output:

- `docs/reports/weekly-report-{teams}-{seasons}-{report_date}.json`

Default HTML output:

- same base name with `.html`

Examples:

- `docs/reports/weekly-report-arsenal-20252026-2026-02-25.json`
- `docs/reports/weekly-report-arsenal-20252026-2026-02-25.html`

## Commands

Build JSON only:

```bash
python3 e0_weekly_report_data.py \
  --db data/footstat.sqlite3 \
  --competition E0 \
  --team Arsenal \
  --seasons 2025-2026 \
  --z-threshold 1.8 \
  --regime-effect-threshold 0.7
```

By default, the JSON now also carries `league_context` for the same competition
and season so weekly context export can compute league-relative comparisons from
the report artifact itself. Use `--no-league-context` to disable that.

To build a report "as of" an earlier point in the season without leaking future
matches into any derived summaries, use:

```bash
python3 e0_weekly_report_data.py \
  --db data/footstat.sqlite3 \
  --competition E0 \
  --team Arsenal \
  --seasons 2025-2026 \
  --through-week 28
```

`--through-week` is applied during report generation, before weekly rows,
detectors, league context, rankings, and story pegs are computed.

Render HTML from JSON:

```bash
python3 e0_weekly_report_html.py \
  --in docs/reports/weekly-report-arsenal-20252026-2026-02-25.json \
  --style cinematic
```

One-command runner (JSON + HTML):

```bash
python3 e0_weekly_report_run.py \
  --db data/footstat.sqlite3 \
  --competition E0 \
  --team Arsenal \
  --seasons 2025-2026 \
  --z-threshold 1.8 \
  --regime-effect-threshold 0.7 \
  --report-style cinematic
```

Export compact weekly context for LLM ideation:

```bash
python3 e0_weekly_context_export.py \
  --report-json docs/reports/weekly-report-arsenal-20252026-2026-02-26.json \
  --team Arsenal \
  --season 2025-2026 \
  --week 28 \
  --out docs/reports/weekly-context-arsenal-20252026-w28-2026-02-26.json
```

Optional extra overlay (rankings, extra anomalies, custom fields):

```bash
python3 e0_weekly_context_export.py \
  --report-json docs/reports/weekly-report-arsenal-20252026-2026-02-26.json \
  --extra-json docs/weekly_context_extra.json
```

Starter overlay template:

- `docs/weekly_context_extra.example.json`

Current weekly context export adds a few derived sections beyond the raw match
snapshot:

- `form_snapshot` for recent form totals over the selected window
- `trend_summary` for simple recent slopes/directions on numeric metrics
- `largest_upward_deltas` / `largest_downward_deltas` for clearer direction-of-change summaries
- `week_flags` for concise standout observations
- `week_extremes` for structured season-relative highs/lows
- `season_rankings` for current-week rank within the selected team's season
- `league_relative` for same-week comparison against other teams in the report or `league_context`
- `league_relative.season_to_date_metrics` for peer ranking based on season-to-date averages through the selected week
- `league_relative.percentile_trends` for recent movement in same-week peer percentile
- `league_relative.top_percentile_movers` for explicit top rising/falling peer-percentile metrics
- `context_quality` for confidence and guardrail metadata
- `story_pegs` for deterministic editorial candidates before LLM handoff
- `chart_hooks` for plot suggestions grounded in the exported context
- `data_gaps` to make missing peer context explicit

The chart hook list now includes peer-oriented hooks as well, including:

- peer percentile movement lines
- season-to-date peer rank summary hooks

## LLM handoff workflow

Use these companion prompt files to keep weekly ChatGPT sessions consistent:

- `docs/prompts/weekly_ideation_prompt.md`
- `docs/prompts/weekly_blog_prompt.md`
- `docs/weekly_runbook.md`

The prompt companions are tuned to consume the richer weekly context sections,
especially:

- `story_pegs`
- `week_flags`
- `week_extremes`
- `season_rankings`
- `league_relative.metrics`
- `league_relative.season_to_date_metrics`
- `league_relative.percentile_trends`
- `league_relative.top_percentile_movers`
- `chart_hooks`

OpenAI API automation is available as an alternative to the ChatGPT web UI.
Set:

```bash
export OPENAI_API_KEY=...
export OPENAI_MODEL=gpt-5
```

Suggested flow:

1. Generate weekly report JSON/HTML.
2. Export one-week context JSON with `e0_weekly_context_export.py`.
3. Paste ideation prompt + context JSON into ChatGPT to get story candidates.
4. Optionally write an editorial-selection artifact recording which story you chose.
5. Paste blog prompt + selected candidate to generate the weekly draft post.

Operational note:

- use a fresh ChatGPT session for each week's ideation pass
- this helps reduce prior-week framing carryover, which can otherwise bias the
  model toward season-trend stories when a match-specific story is the better lead

Editorial selection helper:

```bash
python3 e0_weekly_editorial_select.py \
  --ideation-json docs/reports/weekly-chatgptresponse-arsenal-20252026-w27-2026-02-28-round3.json \
  --context-json docs/reports/weekly-context-arsenal-20252026-w27-2026-02-28.json \
  --story-id S1 \
  --secondary-story-id S2 \
  --reason "Best match-specific lead with strongest corroboration."
```

Blog-draft helper packet after you have the editorial selection:

```bash
python3 e0_weekly_blog_packet.py \
  --selection-json docs/reports/editorial-selection-arsenal-20252026-w27-2026-02-28.json \
  --write-default
```

That writes a markdown packet into `exports/` with:

- the blog prompt path
- the selected story JSON
- the weekly context JSON path
- the target markdown draft path to save the ChatGPT response into

Or generate the markdown draft directly via the OpenAI API:

```bash
python3 e0_weekly_blog_generate.py \
  --selection-json docs/reports/editorial-selection-arsenal-20252026-w27-2026-02-28.json \
  --overwrite
```

Likewise, ideation JSON can be generated directly from the weekly context:

```bash
python3 e0_weekly_ideate_generate.py \
  --context-json docs/reports/weekly-context-arsenal-20252026-w27-2026-02-28.json \
  --overwrite
```

Minimal site generator from those artifacts:

```bash
python3 e0_site_build.py \
  --team Arsenal \
  --season 2025-2026
```

This produces a simple static portal under `docs/site/`:

- `docs/site/index.html`
- `docs/site/arsenal/2025-2026/index.html`
- `docs/site/arsenal/2025-2026/week-<n>.html`

The week pages render the selected story, summary context, signal cards, and
relative links back to the underlying artifact files.

Optional content is included automatically when present in `docs/reports/`:

- `weekly-post-arsenal-20252026-w<n>.md`
- `weekly-blog-arsenal-20252026-w<n>.md`
- `blog-draft-arsenal-20252026-w<n>.md`
- `publication-notes-arsenal-20252026-w<n>.md`
- `publication-notes-arsenal-20252026-w<n>.json`

Optional helper to print the exact prompt/context/report files for a given week:

```bash
python3 e0_weekly_prompt_packet.py \
  --report-json docs/reports/weekly-report-arsenal-20252026-2026-02-26.json \
  --team Arsenal \
  --season 2025-2026 \
  --week 28
```

Or write a reusable markdown packet into `exports/`:

```bash
python3 e0_weekly_prompt_packet.py \
  --report-json docs/reports/weekly-report-arsenal-20252026-2026-02-26.json \
  --team Arsenal \
  --season 2025-2026 \
  --week 28 \
  --write-default
```

By default, the runner also generates embedded animation assets and includes
them in the HTML report:

- half-win animated chart
- metric animated chart (default metric: `opponent_fouls`)

Controls:

- `--no-embed-animations`
- `--embed-metric <metric_name>`
- `--embed-style classic|cinematic`
- `--embed-interval-ms <ms>`
- `--annotations <path.json>` (attach per-team/per-season/per-week notes/media)

Annotation config formats supported:

- list of entries
- object with `entries`
- team->(season->week or week)->payload mapping

Example:

```json
{
  "entries": [
    {
      "team": "Arsenal",
      "season": "2025-2026",
      "week": 28,
      "type": "event",
      "title": "North London derby result",
      "note": "Strong transition game in second half.",
      "media_url": "https://example.com/highlights"
    }
  ]
}
```

Suggested annotation `type` values:

- `event`
- `injury`
- `tactical`
- `media`

The report page color-codes annotation cards/chips by `type`.
