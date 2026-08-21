# Completion audit — 2026-08-21

This audit separates locally reproducible engineering completion from the
longitudinal product definition of done in `PLAN.md`. A synthetic fixture cannot
substitute for researcher judgments or four weeks of daily use.

## Reproducible evidence

Run from the repository root:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q src tests
.venv/bin/research-radar evaluate \
  --project examples/synthetic-project \
  --fixture tests/fixtures/golden-candidates.json
.venv/bin/python <codex-skill-creator>/scripts/quick_validate.py \
  .agents/skills/research-radar
```

Observed on 2026-08-21:

- 38 tests passed;
- all source and test modules compiled;
- the repository skill validated;
- a version 0.2.0 wheel installed and initialized a project in a fresh Python
  3.9 virtual environment;
- Research Radar precision@5/10 was 1.00/1.00 on the 20-paper synthetic fixture,
  versus 0.60/0.70 for the title-and-abstract keyword baseline;
- a live Semantic Scholar probe accepted the actual API response shape and
  exposed publisher-elided references as an adapter coverage gap;
- the two-paper U of T/INFORMS access result remains documented in
  `docs/access-validation-2026-08-21.md`.

## Milestone status

| Milestone | Engineering status | Evidence or remaining condition |
| --- | --- | --- |
| A0 / M3 access | Complete for the intended one-paper workflow | Subscription and open-access PDFs were imported, validated, deduplicated, recorded, and exported to page-delimited text. `access resolve` now ranks OA, Crossref, LibKey, and DOI routes. Interactive U of T authentication remains a deliberate human boundary. |
| M0 specification | Engineering fixture complete; user validation pending | Schemas, synthetic project, feedback vocabulary, and 20 judged candidates exist. An anonymized real-project fixture and confirmation that two researchers can fill the profile without help are not yet available. |
| M1 ingestion | Complete for the tested scope | TeX dependencies, referenced BibTeX files, DOI/arXiv identities, duplicates, fingerprints, SQLite migration, idempotence, and explicit profile-change approval are tested. |
| M2 discovery | Complete for the local beta | Crossref, OpenAlex, and Semantic Scholar run behind isolated adapters. Forward citations, related works, backward references, keywords, authors, venues, INFORMS/UTD24 presets, deduplication, caching, retry, provenance, and partial failures are implemented. Provider coverage remains inherently incomplete. |
| M4 distillation/ranking | Engineering contract complete; researcher calibration pending | Typed JSON validation, evidence gating, append-only storage, report hydration, paper-type guidance, explainable feature traces, and keyword-baseline lift are implemented. A real 20-paper-per-project calibration set is still required. |
| M5 reports/feedback | Complete for deterministic local use | Daily delta, empty-day behavior, feedback suppression, audit manifests, weekly synthesis, and full-text queue are tested. Repeated same-window runs are idempotent. |
| M6 skill/automation | Skill and task recipe complete; actual task not installed | The skill validates and the local workflow was manually exercised. Creating the real desktop scheduled task requires a selected research-project directory and the user's ChatGPT task UI/session. |
| M7 sharing | Local package complete; public release evidence pending | Wheel installation, docs, schemas, three profile examples, privacy guidance, issue template, contribution guide, changelog, and plugin evaluation exist. No GitHub remote is configured, GitHub CLI is not authenticated, and two external onboarding reports do not yet exist. |

## Remaining external gates

Only the following items cannot be honestly completed from the repository alone:

1. select the first real research folder, add or approve its substantive
   `RESEARCH_PROFILE.md`, and choose the daily run time;
2. authenticate GitHub CLI (or create a remote manually) before publishing;
3. collect at least 20 judgments on each of two real projects;
4. observe four consecutive weeks of useful incremental briefings and record
   onboarding friction from the second researcher.

Until those gates are met, version 0.2.0 is an installable local beta, not a
validated version 1 product.
