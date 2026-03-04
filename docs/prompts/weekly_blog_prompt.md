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

You are writing a short football analytics article for human readers.

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
- do not use em dashes (`—`) in output text; use commas, colons, or parentheses instead
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
- write for a reader, not for a model evaluator
- do not sound like a checklist, notebook, or post-match template
- do not mirror the prompt outline literally in the prose
- choose only the 2-4 most relevant signals; do not force every available stat into the article
- prefer one sharp football sentence over three mechanical explanatory sentences
- describe what the match felt like in football terms, then use the numbers to support that reading
- vary sentence openings and rhythm; avoid repeated “the practical takeaway is”, “what this means is”, or “the match was defined by” phrasing unless truly needed
- after drafting, revise once to remove template language, repeated ideas, and schema echoes
- keep one central thread; the article should feel like one argument, not several stitched observations
- if a stat does not materially strengthen the story, leave it out of the main prose
- body paragraphs should blend evidence and meaning naturally rather than toggling between them
- headings should sound like football writing, not report labels
- use the appendix for receipts, not as overflow for half-formed points

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
- `next_fixture`
- `next_opponent_last_week`
- `next_opponent_recent_form`
- `next_week_matchup_lens`

Write output with this shape:

- `Headline`
- `Subheading`
- `Body`
  - 2-4 natural subheads in normal English
  - not numbered
  - not templated labels like "What happened this week" or "What the peer context says"
- `What to look for next week`
  - short closing bullets
  - if `next_fixture` exists, mention the opponent by name explicitly in this section
  - if `next_opponent_last_week` exists, include at least one bullet that references that opponent's most recent match pattern
  - if `next_opponent_recent_form` or `next_week_matchup_lens` exists, include at least one us-vs-them bullet grounded in those fields
  - if `next_week_matchup_lens.top_beneficial` / `top_harmful` exist, prioritize those top two deltas before any weaker matchup notes
- `Data appendix`
  - exact metrics and field names go here, not in the main prose

Important:
- do not print numbered labels like `1) Title` or `2) One-paragraph thesis`
- do not expose internal scaffolding
- the main article should read like an actual piece, not like filled slots
- forbidden output patterns:
  - `1) Title`
  - `2) One-paragraph thesis`
  - `3) What happened this week`
  - `4) What the peer context says`
  - em-dash punctuation like `this thing — that thing`
  - `Facts:`
  - `Reading:`
  - `Interpretation:`
  - `Takeaway:`
  - `What happened this week`
  - `What the peer context says`
  - `Why it might matter`
- bad:
  - `1) Title`
  - `Arsenal ...`
- bad body style:
  - `Facts: Arsenal earned eight corners...`
  - `Reading: This suggests...`
  - `Takeaway: Arsenal must improve...`
- good:
  - `# Arsenal ...`
  - or just the headline itself on the first line
- good body style:
  - `Arsenal earned eight corners at Anfield, which suggests they found territory often enough; the problem was what happened once the ball arrived.`
- if you find yourself writing numbered labels, stop and rewrite the piece before returning it
- do not structure body paragraphs as paired labels like `Facts:` and `Reading:`
- blend observation and interpretation into normal prose
- if a paragraph starts with `Facts:` or `Reading:`, rewrite it before returning the article

Length target:
- 450-700 words

Style notes:
- no fake certainty
- no invented metrics
- short paragraphs
- include one concise callout sentence suitable for social sharing
- do not merely list numbers; explain what they say about how the match felt or how the team played
- use connective language sparingly; do not rely on the same phrasing repeatedly
- avoid repeating metric names mechanically if a plain-English explanation would be clearer
- make the headline, subheading, and body readable to a smart general football reader, not only someone who knows the schema
- in the main prose, prefer terms like `shots`, `corners`, `goals conceded`, `attempts allowed`, `fouls drawn`, `bookings`, `recent form`, or other natural football phrasing
- translate ranking data into normal English, e.g. `best in the league that week`, `second-best defensive mark`, `among the top teams`, rather than `rank 1/20`
- reserve exact JSON field names for the `Data appendix`
- integrate the numbers into the sentence rather than announcing them with labels
- headings should be short, specific, and writerly
- do not over-explain obvious football meaning once the point is clear
- if a paragraph feels like it is just unpacking a stat mechanically, rewrite it in more natural football language
- trim one sentence from any paragraph that feels bloated or repetitive
- if peer-relative and team-relative readings disagree, explain that clearly
- in the `Data appendix`, cite exact metric names from the JSON
- if `context_quality.overall_confidence` is low, say so plainly in the caveats section
- if a chosen story candidate aligns with a `story_pegs` entry, preserve that linkage in the writeup
- if a sparse metric is included, explain why it remains secondary or why corroboration makes it worth mentioning
- interpret delta fields as direction-of-change fields, not inherently positive/negative for the team
- for opponent metrics, explain whether an increase/decrease is good or bad for the selected team
- prefer `largest_upward_deltas` / `largest_downward_deltas` if present
- keep caveats/data gaps focused on football-data limitations, not prompt/session limitations
