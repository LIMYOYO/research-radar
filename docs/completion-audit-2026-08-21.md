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

- 52 tests passed;
- all source and test modules compiled;
- the repository skill validated;
- a version 0.2.0 wheel installed and initialized a project in a fresh Python
  3.9 virtual environment;
- Research Radar precision@5/10 was 1.00/1.00 on the 20-paper synthetic fixture,
  versus 0.60/0.70 for the title-and-abstract keyword baseline;
- the same fixture had 100% persistent identifiers, 100% explicit identity
  contract coverage, and a 0% duplicate-identity rate;
- a live Semantic Scholar probe accepted the actual API response shape and
  exposed publisher-elided references as an adapter coverage gap;
- the two-paper U of T/INFORMS access result remains documented in
  `docs/access-validation-2026-08-21.md`.

## Read-only real-project preflight

Two existing private repositories were inspected without modifying either
worktree. The mature project exposes 80 bibliography seeds (74 cited in the
active manuscript, 4 with persistent identifiers); the early project exposes 8
seeds (none yet cited, 1 with a persistent identifier). Both have ordinary
software/project READMEs rather than the required research distill, so the
correct current result is `doctor` exit code 2 with all ten profile sections
listed as missing. This prevents a scheduled task from silently searching on a
repository description instead of the researcher's actual framework.

## Milestone status

| Milestone | Engineering status | Evidence or remaining condition |
| --- | --- | --- |
| A0 / M3 access | Complete for the intended one-paper workflow | Subscription and open-access PDFs were imported, validated, deduplicated, recorded, and exported to page-delimited text. `access acquire` now attempts one bounded public/OA download and automatically exports successful text; 403/HTML responses return a clean LibKey handoff. The live U of T browser chain was repeated without another Duo prompt. Interactive authentication remains a deliberate human boundary. |
| M0 specification | Engineering fixtures complete; user validation pending | Schemas, synthetic project, feedback vocabulary, and 20 judged candidates exist. An open-source-safe fixture now preserves the nested/multi-file dependency shapes observed in private projects while replacing every substantive field. Confirmation that two researchers can fill the profile without help remains external. |
| M1 ingestion | Complete for the tested scope | TeX dependencies, referenced BibTeX files, 20 DOI normalization cases, DOI/arXiv identities, explicit title-fallback status, malformed-BibTeX diagnostics, duplicates, fingerprints, SQLite migration, idempotence, explicit profile-change approval, and rejection of generic READMEs as research profiles are tested. |
| M2 discovery | Complete for the local beta | Crossref, OpenAlex, and Semantic Scholar run behind isolated adapters. Forward citations, related works, backward references, keywords, authors, venues, INFORMS/UTD24 presets, deduplication, caching, retry, provenance, and partial failures are implemented. Provider coverage remains inherently incomplete. |
| M4 distillation/ranking | Engineering contract complete; researcher calibration pending | Typed JSON validation, evidence gating, append-only storage, report hydration, paper-type guidance, explainable feature traces, and keyword-baseline lift are implemented. A real 20-paper-per-project calibration set is still required. |
| M5 reports/feedback | Complete for deterministic local use | Daily delta, empty-day behavior, feedback suppression, audit manifests, weekly synthesis, and full-text queue are tested. Repeated same-window runs are idempotent. |
| M6 skill/automation | Skill and task recipe complete; actual task not installed | The skill validates, both candidate real projects have been preflighted read-only, and incomplete profiles now stop before network work or state persistence. Creating the real desktop scheduled task still requires a selected research-project directory, completed profile, and the user's ChatGPT task UI/session. |
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
