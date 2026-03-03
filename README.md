# Fun analysis of footy

The purpose of this repo is to help refresh and learn more stats by way of
analysis of sports data. Really, I am focusing on football (soccer).


# Use

```
$ python3 -m venv .
$ source bin/activate
$ python3 -m pip install -r requirements.txt 
```

# Data

## Football-data.co.uk

**inset some comment**

See `data/football-data.co.uk/notes.txt` for demystifying the symbols in the CSV.

Getting premier league data:

```
$ curl -o data/football-data.co.uk/E0.csv https://www.football-data.co.uk/mmz4281/2526/E0.csv
```

## Weekly half-win animation (interactive)

Generate an interactive HTML plot where each point can be clicked for a per-week
summary (and optional attached media):

```
$ python3 e0_weekly_halfwin_animate.py \
    --team Arsenal,Fulham \
    --style cinematic \
    --interval-ms 500 \
    --media-config docs/media_config_example.json \
    --out docs/arsenal_fulham_weekly_halfwin_animated.html
```

## Multi-season overlays

Static SVG across multiple E0 seasons:

```
$ python3 e0_multi_season_halfwin_plot.py \
    --team Arsenal \
    --seasons 20212022,20222023,20232024,20242025,2025-2026 \
    --out docs/arsenal_multi_season_halfwin.svg
```

Animated HTML across multiple E0 seasons:

```
$ python3 e0_multi_season_halfwin_animate.py \
    --team Arsenal,Fulham \
    --style cinematic \
    --interval-ms 500 \
    --out docs/arsenal_fulham_multi_season_halfwin_animated.html
```

## SQLite bootstrap (phase 1)

Initialize the local database schema:

```
$ python3 footstat_db_init.py --db data/footstat.sqlite3 --show-tables
```

## E0 ingest to SQLite

Ingest all matching E0 CSV files from a directory:

```
$ python3 e0_ingest_db.py \
    --db data/footstat.sqlite3 \
    --data-dir data/football-data.co.uk \
    --glob "E0*.csv"
```

Preview ingest only (no writes):

```
$ python3 e0_ingest_db.py \
    --db data/footstat.sqlite3 \
    --data-dir data/football-data.co.uk \
    --dry-run
```

Replace existing source data for each source key before ingest:

```
$ python3 e0_ingest_db.py \
    --db data/footstat.sqlite3 \
    --data-dir data/football-data.co.uk \
    --replace-source
```

## Run existing E0 tools from DB

Correlation from DB:

```
$ python3 e0_corr.py \
    --source db \
    --db data/footstat.sqlite3 \
    --team Arsenal \
    --seasons 2025-2026
```

Weekly static SVG from DB:

```
$ python3 e0_weekly_halfwin_plot.py \
    --source db \
    --db data/footstat.sqlite3 \
    --team Arsenal \
    --seasons 2025-2026 \
    --out docs/arsenal_weekly_halfwin_db.svg
```

Weekly animated HTML from DB:

```
$ python3 e0_weekly_halfwin_animate.py \
    --source db \
    --db data/footstat.sqlite3 \
    --team Arsenal \
    --seasons 2025-2026 \
    --out docs/arsenal_weekly_halfwin_db_animated.html
```

For a full end-to-end DB workflow, see `docs/e0_db_workflow.md`.

## Weekly metric plot (custom field)

Plot a normalized metric by week (example: `opponent_fouls`):

```
$ python3 e0_weekly_metric_plot.py \
    --source db \
    --db data/footstat.sqlite3 \
    --team Arsenal \
    --seasons 2025-2026 \
    --metric opponent_fouls \
    --out docs/arsenal_weekly_opponent_fouls.svg
```

Multi-season static version from DB (separate line per season):

```
$ python3 e0_weekly_metric_plot.py \
    --source db-multi \
    --db data/footstat.sqlite3 \
    --team Arsenal \
    --seasons 2024-2025,2025-2026 \
    --metric opponent_fouls \
    --out docs/arsenal_db_multi_season_weekly_opponent_fouls.svg
```

Animated version:

```
$ python3 e0_weekly_metric_animate.py \
    --source db \
    --db data/footstat.sqlite3 \
    --team Arsenal \
    --seasons 2025-2026 \
    --metric opponent_fouls \
    --interval-ms 500 \
    --out docs/arsenal_weekly_opponent_fouls_animated.html
```

Multi-season animated version from CSV files (`E0.csv` + `E0-YYYYYYYY.csv`):

```
$ python3 e0_weekly_metric_animate.py \
    --source csv-multi \
    --data-dir data/football-data.co.uk \
    --team Arsenal \
    --seasons 2024-2025,2025-2026 \
    --metric opponent_fouls \
    --style cinematic \
    --interval-ms 500 \
    --out docs/arsenal_multi_season_weekly_opponent_fouls_animated.html
```

Multi-season animated version from DB (separate line per season):

```
$ python3 e0_weekly_metric_animate.py \
    --source db-multi \
    --db data/footstat.sqlite3 \
    --team Arsenal \
    --seasons 2024-2025,2025-2026 \
    --metric opponent_fouls \
    --style cinematic \
    --interval-ms 500 \
    --out docs/arsenal_db_multi_season_weekly_opponent_fouls_animated.html
```

## Weekly report pipeline (phase 1)

Generate weekly report JSON from DB:

```
$ python3 e0_weekly_report_data.py \
    --db data/footstat.sqlite3 \
    --competition E0 \
    --team Arsenal \
    --seasons 2025-2026 \
    --z-threshold 1.8 \
    --regime-effect-threshold 0.7
```

This now includes same-season league context by default so downstream weekly
context export can compare Arsenal to peer teams for the same week. Use
`--no-league-context` to keep the JSON smaller.

To generate an "as of week N" report without leaking future weeks into trends,
rankings, or story pegs:

```bash
python3 e0_weekly_report_data.py \
  --db data/footstat.sqlite3 \
  --competition E0 \
  --team Arsenal \
  --seasons 2025-2026 \
  --through-week 28
```

Render HTML from that JSON:

```
$ python3 e0_weekly_report_html.py \
    --in docs/reports/weekly-report-arsenal-20252026-2026-02-25.json \
    --style cinematic
```

Or run both in one command:

```
$ python3 e0_weekly_report_run.py \
    --db data/footstat.sqlite3 \
    --competition E0 \
    --team Arsenal \
    --seasons 2025-2026 \
    --z-threshold 1.8 \
    --regime-effect-threshold 0.7 \
    --report-style cinematic
```

Runner behavior also includes league context by default; disable with
`--no-league-context` if you only want the selected team blocks.
Use `--through-week <N>` here as well to build an "as of week N" report.

`e0_weekly_report_run.py` now also generates embedded animation assets by default
(half-win + one metric) and includes them in the report HTML via iframes.
Use `--no-embed-animations` to disable, or tune with:

- `--embed-metric opponent_fouls`
- `--embed-style classic|cinematic`
- `--embed-interval-ms 500`
- `--annotations docs/weekly_annotations.json` (attach per-week notes/media)

For annotations, optional `type` values (`event`, `injury`, `tactical`, `media`)
are color-coded in the report and finding cards.

For contract details, see `docs/weekly_report_pipeline.md`.

## Weekly context export (for ChatGPT ideation)

Export compact "this week" context JSON from a weekly report artifact:

```
$ python3 e0_weekly_context_export.py \
    --report-json docs/reports/weekly-report-arsenal-20252026-2026-02-26.json \
    --team Arsenal \
    --season 2025-2026 \
    --week 28 \
    --out docs/reports/weekly-context-arsenal-20252026-w28-2026-02-26.json
```

Optional overlay for extra context fields (for example rankings/xG context):

```
$ python3 e0_weekly_context_export.py \
    --report-json docs/reports/weekly-report-arsenal-20252026-2026-02-26.json \
    --extra-json docs/weekly_context_extra.json
```

Use `docs/weekly_context_extra.example.json` as a starter template.

The exported context now includes richer derived fields intended to improve LLM
ideation quality:

- `form_snapshot` - recent W/D/L, points, half-win average, goal totals
- `trend_summary` - simple per-metric direction and slope over the recent window
- `largest_upward_deltas` / `largest_downward_deltas` - clearer directional change summaries vs season average
- `week_flags` - short standout summaries for the selected week
- `week_extremes` - structured season-relative high/low markers for that week
- `season_rankings` - current-week value rank within the selected team's season
- `league_relative` - same-week comparison vs other teams present in the report or `league_context`
- `league_relative.season_to_date_metrics` - peer ranking using season-to-date averages through the selected week
- `league_relative.percentile_trends` - recent movement in same-week peer percentile
- `league_relative.top_percentile_movers` - explicit top rising/falling peer-percentile metrics
- `context_quality` - confidence, sample-size, flat-signal, and peer-context guardrails
- `story_pegs` - deterministic editorial candidates generated before LLM handoff
- `chart_hooks` - prebuilt chart ideas tied to the standout metrics
- `data_gaps` - explicit notes when comparative context could not be built

`chart_hooks` now also includes peer-oriented suggestions such as:

- peer percentile movement charts
- season-to-date peer rank summary charts

## ChatGPT companion prompts

Prompt templates for consistent weekly ideation/blog drafts:

- `docs/prompts/weekly_ideation_prompt.md`
- `docs/prompts/weekly_blog_prompt.md`
- `docs/weekly_runbook.md`

API-driven LLM automation is also available now, using the OpenAI Responses API
directly via Python stdlib HTTP calls. No extra Python dependency is required.

Environment:

```bash
export OPENAI_API_KEY=...
export OPENAI_MODEL=gpt-5
```

These now explicitly steer ChatGPT to use:

- `story_pegs`
- `week_flags` / `week_extremes`
- `season_rankings`
- `league_relative.metrics`
- `league_relative.season_to_date_metrics`
- `league_relative.percentile_trends`
- `league_relative.top_percentile_movers`
- `chart_hooks`

Quick workflow:

1) Export weekly context JSON:

```bash
python3 e0_weekly_context_export.py \
  --report-json docs/reports/weekly-report-arsenal-20252026-2026-02-26.json \
  --team Arsenal \
  --season 2025-2026 \
  --week 28 \
  --out exports/weekly-context-arsenal-w28.json
```

2) In ChatGPT, paste:
   - `docs/prompts/weekly_ideation_prompt.md`
   - `exports/weekly-context-arsenal-w28.json`

3) Pick a story, then paste:
   - `docs/prompts/weekly_blog_prompt.md`
   - chosen story candidate + same weekly context JSON

Recommended practice:

- use a fresh ChatGPT session for each week's ideation run
- this reduces prior-week framing bias, especially when deciding between
  match-specific stories and broader season-trend stories

Optional editorial-selection artifact after you choose the story:

```bash
python3 e0_weekly_editorial_select.py \
  --ideation-json docs/reports/weekly-chatgptresponse-arsenal-20252026-w27-2026-02-28-round3.json \
  --context-json docs/reports/weekly-context-arsenal-20252026-w27-2026-02-28.json \
  --story-id S1 \
  --secondary-story-id S2 \
  --reason "Best weekly lead with strongest match-specific explanation."
```

If you want a copy/paste packet for the blog-draft step after selection:

```bash
python3 e0_weekly_blog_packet.py \
  --selection-json docs/reports/editorial-selection-arsenal-20252026-w27-2026-02-28.json \
  --write-default
```

That writes a markdown helper packet such as:

- `exports/weekly-blog-packet-arsenal-20252026-w27.md`

The packet tells you exactly what to paste into ChatGPT and where to save the
returned markdown draft.

Generate ideation JSON directly with the API:

```bash
python3 e0_weekly_ideate_generate.py \
  --context-json docs/reports/weekly-context-arsenal-20252026-w27-2026-02-28.json
```

That writes:

- `docs/reports/weekly-chatgpt-ideate-w27.json`

Generate the weekly markdown post directly with the API after selection:

```bash
python3 e0_weekly_blog_generate.py \
  --selection-json docs/reports/editorial-selection-arsenal-20252026-w27-2026-02-28.json \
  --overwrite
```

That writes:

- `docs/reports/weekly-post-arsenal-20252026-w27.md`

Useful flags on both commands:

- `--model ...`
- `--dry-run`
- `--overwrite`
- `--store` / `--no-store`

If the ideation response is large, increase `--max-output-tokens`. The script
now writes debug artifacts (`.raw.txt` and `.response.json`) if the API returns
an incomplete/truncated response.

Optional helper to print a paste-ready packet for a specific week:

```bash
python3 e0_weekly_prompt_packet.py \
  --report-json docs/reports/weekly-report-arsenal-20252026-2026-02-26.json \
  --team Arsenal \
  --season 2025-2026 \
  --week 28
```

Minimal static site build from the generated weekly artifacts:

```bash
python3 e0_site_build.py \
  --team Arsenal \
  --season 2025-2026
```

That writes:

- `docs/site/index.html`
- `docs/site/arsenal/2025-2026/index.html`
- `docs/site/arsenal/2025-2026/week-<n>.html`

The site pages use the existing weekly context, ideation, and editorial-selection
artifacts and keep internal links relative.

Optional week-page content is picked up automatically when these files exist in
`docs/reports/`:

- `weekly-post-arsenal-20252026-w<n>.md`
- `weekly-blog-arsenal-20252026-w<n>.md`
- `blog-draft-arsenal-20252026-w<n>.md`
- `publication-notes-arsenal-20252026-w<n>.md`
- `publication-notes-arsenal-20252026-w<n>.json`

Write that packet to the default `exports/` location instead of stdout:

```bash
python3 e0_weekly_prompt_packet.py \
  --report-json docs/reports/weekly-report-arsenal-20252026-2026-02-26.json \
  --team Arsenal \
  --season 2025-2026 \
  --week 28 \
  --write-default
```
