# Codex prompt: review + fixes for weekly report HTML generator

You are editing `render_weekly_report_html.py` (the script pasted in this chat). Make **surgical** changes only. Preserve formatting and existing behavior unless explicitly changed below.

## What to check
1. Story extraction should **never** mistakenly treat a filesystem path string as story text.
2. "Event / Media Annotations" panel should be **omitted entirely** when there are no annotations.
3. Avoid infinite recursion / cycles while searching nested story containers (already uses `seen`; keep it).
4. Do not introduce new dependencies.

## Confirmed good in the current version
- Annotations panel is already conditional: `_render_annotations()` returns `""` when none, and `annotations_panel` is only included when `annotations_html` is truthy. Keep this behavior.
- `_search_story_container(..., seen=...)` cycle guard exists. Keep it.

## Fixes to implement

### Fix 1: Prevent dict “content/body/markdown/etc” fields from returning path-like strings as story text
Right now `_extract_candidate_story_text()` filters path-like strings only when `value` is a **string** at the top level.  
But when `value` is a **dict**, it returns `candidate.strip()` for keys like `"content"`, `"markdown"`, `"text"`, etc without checking if the candidate is actually a path (e.g. `"./writeups/week12.md"`). If the file is missing or unreadable, you end up rendering the path string into the report.

**Change:**
- Add a small helper: `_looks_like_path_string(text: str) -> bool`
  - True when text starts with `"./"` or `"../"`, contains `"/"` or `"\\"`, or ends with typical extensions (`.md`, `.markdown`, `.txt`, `.html`, `.htm`).
- In `_extract_candidate_story_text()` dict branch: when `candidate` is a non-empty string:
  - If `_looks_like_path_string(candidate)`: return `None` (do not treat as text)
  - Else return the stripped text as before

This keeps path resolution centralized in `_extract_story_from_path_dict` and `_extract_story_from_path_string`.

**Acceptance test:**
- If JSON contains `{"narrative": {"markdown": "./foo.md"}}` and `foo.md` does not exist, the page should **not** render `"./foo.md"` as story content.
- If JSON contains `{"narrative": {"markdown": "# Headline\nBody..."}}`, it should still render as story.

### Fix 2: Reuse the same path heuristic everywhere
Use `_looks_like_path_string()` in both:
- `_extract_candidate_story_text()` string branch (instead of duplicating logic)
- `_extract_story_from_path_string()` (for the `looks_like_path` computation)

This makes behavior consistent and reduces drift.

### Fix 3: Cap story reads consistently and document it
You already cap reads to `[:200_000]` in both `_extract_story_from_path_dict` and `_extract_story_from_path_string`. Keep the cap, but add a brief comment (one line) explaining it prevents huge story files from bloating the HTML.

## Deliverable
- Output a unified diff patch (`diff --git ...`) with the minimal changes implementing Fixes 1–3.
- Do not change anything else.

## Notes
- Do not change escaping behavior: `_render_rich_text()` must keep escaping user content.
- Do not add HTML rendering of raw markdown beyond the current simple parser.
