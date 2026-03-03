# Weekly Runbook

Use this as the default weekly operating procedure for Arsenal weekly ideation.

## 1) Build the weekly report artifact

Current/latest week:

```bash
python3 e0_weekly_report_run.py \
  --db data/footstat.sqlite3 \
  --competition E0 \
  --team Arsenal \
  --seasons 2025-2026
```

Historical week `N` (prevents future leakage into trends/rankings/story pegs):

```bash
python3 e0_weekly_report_run.py \
  --db data/footstat.sqlite3 \
  --competition E0 \
  --team Arsenal \
  --seasons 2025-2026 \
  --through-week N
```

## 2) Export weekly context

Current/latest week:

```bash
python3 e0_weekly_context_export.py \
  --report-json docs/reports/weekly-report-arsenal-20252026-YYYY-MM-DD.json \
  --team Arsenal \
  --season 2025-2026
```

Historical week `N`:

```bash
python3 e0_weekly_context_export.py \
  --report-json docs/reports/weekly-report-arsenal-20252026-through-wN-YYYY-MM-DD.json \
  --team Arsenal \
  --season 2025-2026 \
  --week N
```

## 3) Inspect the context before using ChatGPT

Review these sections first:

- `context_quality`
- `story_pegs`
- `week_flags`
- `largest_upward_deltas`
- `largest_downward_deltas`
- `chart_hooks`

Quick rule:

- if `context_quality.overall_confidence` is `low`, expect more fragile stories and treat peer-relative claims cautiously

## 4) Use a fresh ChatGPT session

Recommended practice:

- use a fresh ChatGPT session for each week's ideation run
- this reduces prior-week framing carryover

Paste:

1. `docs/prompts/weekly_ideation_prompt.md`
2. the weekly context JSON

If you want to skip the web UI and use the OpenAI API instead:

```bash
export OPENAI_API_KEY=...
export OPENAI_MODEL=gpt-5

python3 e0_weekly_ideate_generate.py \
  --context-json docs/reports/weekly-context-arsenal-20252026-w27-2026-02-28.json \
  --overwrite
```

## 5) Evaluate the ideation response

Check:

- did ChatGPT choose the right primary story?
- did it respect `context_quality`?
- did it keep weak/sparse signals secondary?
- is the lead about this week, or did it drift into generic season framing?

## 6) Pick the editorial output

Default target:

- 1 primary story
- 1 secondary/alternate story
- optional 1 weird/sidebar story

Do not force all three if the week is thin.

Optional: record the choice as an artifact:

```bash
python3 e0_weekly_editorial_select.py \
  --ideation-json docs/reports/weekly-chatgptresponse-arsenal-20252026-w27-2026-02-28-round3.json \
  --context-json docs/reports/weekly-context-arsenal-20252026-w27-2026-02-28.json \
  --story-id S1 \
  --secondary-story-id S2 \
  --reason "Best match-specific lead with strongest corroboration."
```

## 7) Draft the post

Paste into ChatGPT:

1. `docs/prompts/weekly_blog_prompt.md`
2. chosen story candidate
3. same weekly context JSON

Or generate a copy/paste packet from the editorial-selection artifact:

```bash
python3 e0_weekly_blog_packet.py \
  --selection-json docs/reports/editorial-selection-arsenal-20252026-w27-2026-02-28.json \
  --write-default
```

That packet tells you:

- what prompt file to paste
- which selected story JSON to paste
- which weekly context JSON to paste
- where to save the returned markdown draft

If you want to generate the markdown draft directly through the API:

```bash
python3 e0_weekly_blog_generate.py \
  --selection-json docs/reports/editorial-selection-arsenal-20252026-w27-2026-02-28.json \
  --overwrite
```

## 8) Build or refresh the static site

After the editorial-selection artifacts exist:

```bash
python3 e0_site_build.py \
  --team Arsenal \
  --season 2025-2026
```

Outputs:

- `docs/site/index.html`
- `docs/site/arsenal/2025-2026/index.html`
- `docs/site/arsenal/2025-2026/week-<n>.html`

Optional week-page content is included automatically when present in
`docs/reports/`, using names like:

- `weekly-post-arsenal-20252026-w<n>.md`
- `publication-notes-arsenal-20252026-w<n>.md`
- `publication-notes-arsenal-20252026-w<n>.json`

## What to trust most

- `context_quality`
- `story_pegs`
- `week_flags`
- `week_extremes`
- `largest_upward_deltas`
- `largest_downward_deltas`

## What to treat carefully

- peer-percentile movers when peer set is tiny
- discipline/referee texture stories
- sparse or flat-signal metrics

## Practical tie-breaker

If the recommended story feels wrong, check whether the model is choosing:

- the best `match story`, or
- the best `season story`

For weekly publishing, prefer the match/week lead unless the season story is clearly stronger.
