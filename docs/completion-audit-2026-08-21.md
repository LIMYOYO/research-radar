# Completion audit — refreshed 2026-08-23

This audit separates locally reproducible engineering completion from the
longitudinal product definition of done in `PLAN.md`. A synthetic fixture cannot
substitute for researcher judgments or four weeks of real on-demand use.

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

Observed through 2026-08-23:

- 74 tests passed locally on Python 3.9, and GitHub Actions passed on Python
  3.9, Python 3.12, and the fresh-wheel package smoke job at commit `2dfd5e1`;
- all source and test modules compiled;
- the repository skill validated;
- version 0.3.2 installed through `scripts/install.sh` in a fresh Python 3.9
  environment; `--version`, synthetic-project initialization, and the complete
  `doctor` readiness check passed;
- the portable installer created an isolated CLI and Codex skill in fresh
  custom paths, then upgraded them in place while preserving the prior skill;
- Research Radar precision@5/10 was 1.00/0.80 on the 20-paper synthetic fixture,
  versus 0.60/0.70 for the title-and-abstract keyword baseline;
- the same fixture had 100% persistent identifiers, 100% explicit identity
  contract coverage, and a 0% duplicate-identity rate;
- a live Semantic Scholar probe accepted the actual API response shape and
  exposed publisher-elided references as an adapter coverage gap;
- the final no-cache MobileAED probe preserved nine candidates while Crossref
  completed, Semantic Scholar exposed two index coverage gaps, and the exhausted
  anonymous OpenAlex daily quota degraded without blocking the overall run;
- the three-paper U of T/INFORMS access result remains documented in
  `docs/access-validation-2026-08-21.md`.

## Version 0.3.2 release record

- `pyproject.toml`, `research_radar.__version__`, README, and changelog all
  identify the current package as 0.3.2.
- The 0.3.2 changes add provider-aware pacing and credentials, bounded recovery
  for long `Retry-After` responses, batched OpenAlex related-work retrieval, and
  explicit Semantic Scholar index-coverage gaps.
- The provider-resilience implementation was CI-verified at commit `2dfd5e1`;
  the `v0.3.2` release commit adds only the audited status-document updates.
- The annotated `v0.3.2` tag and GitHub Release publish the same release commit
  containing this audit.

## Read-only real-project preflight

Two existing private repositories were inspected. The mature MobileAED project
now has a researcher-approved profile, exposes 80 bibliography seeds (74 cited
in the active manuscript, 4 with persistent identifiers), passes `doctor`, and
has completed its first live discovery run. The early project exposes 8 seeds
(none yet cited, 1 with a persistent identifier) and still correctly fails
`doctor` because it has no substantive research profile. This prevents a skill
invocation from silently searching on a generic repository description.

## Milestone status

| Milestone | Engineering status | Evidence or remaining condition |
| --- | --- | --- |
| A0 / M3 access | Complete for the intended one-paper workflow | Subscription and open-access PDFs were imported, identity-verified, deduplicated, recorded, and exported with PDF/text checksum binding. `access acquire` attempts one bounded public/OA download; 403/HTML responses return a clean LibKey handoff. Image-only files require explicit all-page visual confirmation. The live U of T browser chain was repeated without another Duo prompt and a selected INFORMS paper was full-text distilled. Interactive authentication remains a deliberate human boundary. |
| M0 specification | Engineering fixtures complete; user validation pending | Schemas, synthetic project, feedback vocabulary, and 20 judged candidates exist. An open-source-safe fixture now preserves the nested/multi-file dependency shapes observed in private projects while replacing every substantive field. Confirmation that two researchers can fill the profile without help remains external. |
| M1 ingestion | Complete for the tested scope | TeX dependencies, referenced BibTeX files, 20 DOI normalization cases, DOI/arXiv identities, explicit title-fallback status, malformed-BibTeX diagnostics, duplicates, fingerprints, SQLite migration, idempotence, explicit profile-change approval, and rejection of generic READMEs as research profiles are tested. |
| M2 discovery | Complete for the local beta | Crossref, OpenAlex, and Semantic Scholar run behind isolated adapters. Forward citations, related works, backward references, keywords, authors, venues, INFORMS/UTD24 presets, deduplication, caching, bounded `Retry-After`, per-provider success watermarks, material-update detection, provenance, and partial failures are implemented. Provider coverage remains inherently incomplete. |
| M4 distillation/ranking | First real-project calibration implemented; researcher confirmation pending | Typed JSON validation, evidence gating, append-only storage, report hydration, paper-type guidance, explainable feature traces, and honest keyword-baseline comparison are implemented. A private 41-paper provisional MobileAED judgment set now measures precision@5/10 at 1.00/1.00; its labels still require researcher confirmation, and a second real-project set remains external. |
| M5 reports/feedback | Complete for deterministic local use | Incremental delta, no-change behavior, feedback suppression, audit manifests, weekly synthesis, and full-text queue are tested. Repeated same-window runs are idempotent. |
| M6 skill/manual invocation | Complete for the local beta | The skill validates, MobileAED passes project checks and has completed a live run, and incomplete profiles stop before network work or state persistence. The workflow deliberately creates no background schedule. |
| M7 sharing | Version 0.3.2 published; external validation pending | The public repository is available at `https://github.com/LIMYOYO/research-radar`; GitHub Actions passes for the provider-resilience implementation, and the release commit changes only audited status documentation. Fresh wheel/installer checks, docs, schemas, three profile examples, privacy guidance, issue template, contribution guide, changelog, and plugin evaluation exist. Two external onboarding reports do not yet exist. |

## Remaining external gates

Only the following items cannot be honestly completed from the repository alone:

1. collect at least 20 judgments on each of two real projects;
2. observe four consecutive weeks of useful incremental briefings and record
   onboarding friction from the second researcher.

Until those gates are met, version 0.3.2 remains a public beta rather than a
validated version 1 product.
