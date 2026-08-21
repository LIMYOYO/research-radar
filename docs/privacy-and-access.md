# Privacy and access model

Research Radar separates public code from private research state.

## Never committed by default

The repository `.gitignore` excludes `.research-radar/`, `*.pdf`, `papers/`,
and `reports/`. A research project's unpublished TeX and BibTeX remain in that
project and are read without modification. The following artifacts stay local:

- SQLite state and API caches;
- downloaded subscription or open-access PDFs;
- extracted full text;
- generated briefings and researcher feedback;
- access provenance and policy labels.

Run `git status --ignored` before publishing a repository that has been used
with real papers.

## Authentication boundary

The tool opens institution-aware routes and archives files that the user has
already been authorized to download. It does not collect passwords, Duo codes,
browser cookies, or session tokens, and it does not automate bulk retrieval.
Interactive authentication stays in the user's browser.

## Analysis policy

`local-test` is the prototype default: source terms are recorded as advisory and
local text extraction is allowed for the small private test. `strict` blocks
text extraction when the recorded AI-use status is prohibited. Sharing a
briefing never implies permission to redistribute its source PDF or extracted
text.
