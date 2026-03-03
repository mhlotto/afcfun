# Weekly Blog Prompt (From chosen idea + context)

Use this after you pick a story candidate from the ideation prompt output.

## How to use

1. Paste this prompt into ChatGPT.
2. Paste:
   - the selected story candidate
   - the same `weekly_context` JSON
   - any chart outputs or report snippets you want referenced
3. Ask ChatGPT: "Write the blog draft."

## Prompt text

You are writing a short football analytics blog post.

Inputs I will provide:
- `weekly_context` JSON
- selected story candidate
- optional chart/report snippets

Rules:
- stay grounded in provided inputs
- separate observed facts vs interpretation
- include uncertainty/caveats
- keep tone analytical, clear, non-hype
- write like a sharp short football blog post, not a notebook dump
- translate important stats into plain English football meaning
- after citing a metric, explain what it means in normal language
- prefer flowing prose over chains of raw field names
- do not use schema/column names as the main prose unless you are in the data appendix
- do not use raw rank notation like `1/20` or `3/18` in the main prose
- use peer-relative context explicitly when available
- treat sparse, zero-heavy, or low-variance metrics as weak signals by default
- do not let a weak signal dominate the piece unless corroborated by a stronger independent signal
- distinguish:
  - this week vs season-to-date
  - team-relative delta vs peer-relative percentile/rank

Priority evidence sources:
- `story_pegs`
- `largest_upward_deltas`
- `largest_downward_deltas`
- `week_flags`
- `week_extremes`
- `deltas_vs_season_avg`
- `season_rankings`
- `league_relative.metrics`
- `league_relative.season_to_date_metrics`
- `league_relative.percentile_trends`
- `league_relative.top_percentile_movers`
- `context_quality`
- `chart_hooks`

Write output with these sections:

1) Title
2) One-paragraph thesis (3-4 sentences)
3) What happened this week
4) What the peer context says
5) Why it might matter (2-3 hypotheses)
6) What could break this read (caveats)
7) What to watch next week (3 bullets)
8) Data appendix (metrics used and exact values cited)

Length target:
- 450-700 words

Style notes:
- no fake certainty
- no invented metrics
- short paragraphs
- include one concise callout sentence suitable for social sharing
- do not merely list numbers; explain what they say about how the match felt or how the team played
- use connective language such as "in other words", "that suggests", or "the practical takeaway is" when it helps clarity
- avoid repeating metric names mechanically if a plain-English explanation would be clearer
- make the thesis and "what happened this week" sections readable to a smart general football reader, not only someone who knows the schema
- in the main prose, prefer terms like `shots`, `corners`, `goals conceded`, `attempts allowed`, `fouls drawn`, `bookings`, `recent form`, or other natural football phrasing
- translate ranking data into normal English, e.g. `best in the league that week`, `second-best defensive mark`, `among the top teams`, rather than `rank 1/20`
- reserve exact JSON field names for the `Data appendix`
- if peer-relative and team-relative readings disagree, explain that clearly
- in the `Data appendix`, cite exact metric names from the JSON
- if `context_quality.overall_confidence` is low, say so plainly in the caveats section
- if a chosen story candidate aligns with a `story_pegs` entry, preserve that linkage in the writeup
- if a sparse metric is included, explain why it remains secondary or why corroboration makes it worth mentioning
- interpret delta fields as direction-of-change fields, not inherently positive/negative for the team
- for opponent metrics, explain whether an increase/decrease is good or bad for the selected team
- prefer `largest_upward_deltas` / `largest_downward_deltas` if present
- keep caveats/data gaps focused on football-data limitations, not prompt/session limitations
