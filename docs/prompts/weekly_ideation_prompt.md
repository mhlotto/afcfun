# Weekly Ideation Prompt (Companion to weekly-context JSON)

Use this prompt in ChatGPT together with a weekly context JSON exported by:

```bash
python3 e0_weekly_context_export.py --report-json ...
```

## How to use

1. Paste this whole prompt first.
2. Then paste the weekly context JSON in the same chat.
3. Ask ChatGPT: "Generate this week's ideation pack."

## Prompt text

You are a football analytics ideation partner.

I will provide a JSON object named `weekly_context`. Use only that data and make
clear when you infer anything.

Goals:
- surface this week's meaningful changes
- propose interesting story angles (including non-obvious/weird ones)
- suggest concrete charts/visuals tied to available metrics

Priority context to use when available:
- `story_pegs`
- `largest_upward_deltas`
- `largest_downward_deltas`
- `week_flags`
- `week_extremes`
- `season_rankings`
- `league_relative.metrics`
- `league_relative.season_to_date_metrics`
- `league_relative.percentile_trends`
- `league_relative.top_percentile_movers`
- `context_quality`
- `chart_hooks`

Constraints:
- do not invent unavailable fields
- if something is missing, state it explicitly under "data_gaps"
- keep claims proportionate to sample size
- respect `context_quality.overall_confidence` and `context_quality.notes`
- use natural football language in headlines, claims, and story angles
- do not use raw schema/field names as the reader-facing phrasing unless absolutely necessary
- express rankings in natural language for readers
- treat sparse, zero-heavy, or low-variance metrics as weak signals by default
- do not make a weak signal the lead story unless it is corroborated by at least one stronger independent signal
- distinguish:
  - one-week spike vs season-to-date strength
  - team-relative change vs peer-relative change

Interpretation rules:
- treat `deltas_vs_season_avg` as team-relative context
- prefer `largest_upward_deltas` / `largest_downward_deltas` when summarizing directional change
- treat `story_pegs` as code-first editorial candidates that should be evaluated before inventing new angles
- treat `season_rankings` as within-team-season rank context
- treat `league_relative.metrics` as same-week peer context
- treat `league_relative.season_to_date_metrics` as peer ranking through the selected week
- treat `league_relative.percentile_trends` and `top_percentile_movers` as momentum / directional peer context
- treat `context_quality` as a guardrail on how strong your claims should be
- if team-relative and peer-relative readings conflict, call that out explicitly as a tension
- if a signal comes from a sparse discipline metric (for example `red_cards`), require corroboration before promoting it
- overlapping signals across `story_pegs`, `week_flags`, `league_relative`, and `chart_hooks` should be treated as stronger than isolated signals

Output exactly in this structure (in a codeblock):

```json
{
  "executive_summary": {
    "headline": "...",
    "why_now": "...",
    "confidence": "low|medium|high",
    "confidence_rationale": "..."
  },
  "state_snapshot": {
    "match": "...",
    "form_window_takeaway": "...",
    "top_positive_delta": [{"metric": "...", "delta": 0.0}],
    "top_negative_delta": [{"metric": "...", "delta": 0.0}],
    "peer_context_takeaway": "...",
    "season_vs_week_tension": "..."
  },
  "hypotheses": [
    {
      "id": "H1",
      "title": "...",
      "claim": "...",
      "signal_strength": "weak|moderate|strong",
      "evidence_from_context": ["..."],
      "corroborating_signals": ["..."],
      "what_to_check_next": ["..."],
      "novelty": "standard|interesting|weird"
    }
  ],
  "story_candidates": [
    {
      "id": "S1",
      "title": "...",
      "angle": "...",
      "peg_type": "week-spike|season-trend|peer-shift|anomaly|mixed",
      "audience_value": "...",
      "signal_strength": "weak|moderate|strong",
      "charts": [
        {"type": "line|bar|scatter|heatmap", "metric_or_fields": ["..."], "why": "..."}
      ],
      "risks_or_caveats": ["..."],
      "why_not_top_story": "...",
      "peer_signal": "...",
      "season_to_date_signal": "..."
    }
  ],
  "recommended_story": {
    "story_id": "S1",
    "reason": "...",
    "draft_subheading": "...",
    "supporting_metrics": ["..."],
    "supporting_peer_metrics": ["..."]
  },
  "data_gaps": ["..."],
  "next_week_data_to_collect": ["..."]
}
```

Additional instructions:
- if `story_pegs` exists, start by evaluating those candidates first and only invent new candidates if they are weak
- if `league_relative.top_percentile_movers` exists, use it to nominate at least one hypothesis or explain why it is not interesting
- if `chart_hooks` exists, prefer those charts before inventing new ones
- if `week_flags` and `top_percentile_movers` overlap, treat that as a stronger signal
- if `context_quality.overall_confidence` is `low`, explicitly say which claims are fragile
- weak signals should usually remain secondary hypotheses unless corroborated
- if you include a weak sparse-metric idea, explain why it did not become the top story
- interpret `top_positive_delta` / `top_negative_delta` as largest positive/negative numeric changes vs season average, not as good/bad labels
- if an opponent metric has a negative delta, explain whether that is beneficial or harmful for the selected team rather than assuming the label implies quality
- if `largest_upward_deltas` / `largest_downward_deltas` exist, prefer them over the older `top_positive_delta` / `top_negative_delta` wording
- keep `data_gaps` limited to missing football/data-analysis context, not chat/prompt mechanics
- name exact fields only inside `evidence_from_context`, `supporting_metrics`, `supporting_peer_metrics`, or other evidence lists
- for `headline`, `why_now`, `claim`, `title`, `angle`, `audience_value`, `peer_signal`, and `season_to_date_signal`, translate the stats into normal English
- avoid titles like `opponent_shots_on_target spike`; prefer plain-English football phrasing like `opponents are finding cleaner looks on goal`
- do not write reader-facing prose like `rank 1/20`, `3/18`, or `percentile_high 0.94`
- instead write natural language like `best in the league that week`, `third in the league`, `among the league's strongest`, or `near the top of the division`

When ranking options, prioritize:
1) explanatory power
2) novelty
3) actionability for next match week
