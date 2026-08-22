# Changelog

## 0.3.1 — 2026-08-22

- Added a standard `research-radar --version` interface and regression test.
- Corrected public beta version references in the README and completion audit.
- Moved GitHub Actions to the Node 24-based checkout and Python setup releases.

## 0.3.0 — 2026-08-22

- Separated provider-reported availability from verified local PDF/text state
  so reports cannot claim that a provider link is a local full-text file.
- Added continuation-line parsing for project watch keywords, authors, and
  venues, plus project-anchor scoring for detailed research profiles.
- Prevented provider-resolved copies of bibliography titles from appearing as
  new papers and made prose exclusion rules honor their exception conditions.
- Added private identity-only judgment-set evaluation without copying private
  candidate metadata into the public repository.
- Added material-candidate update detection, per-provider successful search
  watermarks, source-window audit output, and bounded `Retry-After` handling.
- Added a persisted latest-change manifest and machine-readable `queue` command
  so the skill can select and complete one paper end to end without parsing
  report prose.
- Bounded live discovery with progress events, a 120-second wall-clock budget,
  conservative query caps, provider circuit breaking after persistent rate
  limits, and no retries for permanent HTTP failures.
- Stopped inferring that every forward citation `extends` a seed; citation edges
  now require textual or deep-reading evidence before that relationship label.
- Added DOI/full-title PDF identity verification, PDF/text checksum binding,
  and explicit all-page visual confirmation for image-only papers.
- Fixed the CLI distillation-import path and completed a live U of T/LibKey/
  EBSCO acquisition plus full-text distillation for an INFORMS article.
- Added a repeatable installer/upgrader for an isolated CLI environment and
  Codex skill, with recoverable skill backups and fresh-install smoke coverage.

## 0.2.0 — 2026-08-21

- Switched the execution contract from background scheduling to researcher-
  initiated `$research-radar` skill invocations and removed scheduler artifacts.
- Added bounded single-DOI automatic PDF acquisition with signature/structure validation, automatic text export, and explicit LibKey authentication fallback.
- Added malformed-BibTeX diagnostics plus explicit persistent/title-fallback identity status and evaluation metrics.
- Prevented generic repository READMEs from masquerading as research profiles;
  discovery now requires a complete project distill before network work begins.
- Added a fresh-wheel GitHub Actions smoke test and public-schema parsing.
- Made `init` idempotently protect generated state through the target clone's
  local Git exclude file without modifying its tracked `.gitignore`.
- Added ranked DOI access resolution across OpenAlex, Crossref, LibKey, and the canonical publisher route.
- Added INFORMS, INFORMS Core, and UTD24 venue presets plus explicit author and venue watch lanes.
- Added Semantic Scholar forward-citation and reference-neighborhood discovery with optional API-key support and partial-failure isolation.
- Added arXiv preprint identity, novelty and priority-risk ranking features, and profile-change approval.
- Added typed deep-distillation context, validation, append-only persistence, and report hydration.
- Added deterministic weekly synthesis and a full-text follow-up queue.
- Added a lexical keyword baseline; the synthetic fixture records precision@5 of 0.60 for keywords and 1.00 for Research Radar.

## 0.1.0 — 2026-08-21

- Added U of T / INFORMS access routing, PDF validation, provenance, and local text export.
- Added TeX, BibTeX, and research-profile ingestion with SQLite state.
- Added Crossref and OpenAlex discovery, deduplication, caching, and failure isolation.
- Added explainable ranking, idempotent Markdown briefings, and researcher feedback.
- Added the repository-scoped Research Radar Codex skill and daily task guide.
- Added a 20-candidate offline golden set and ranking evaluation command.
- Followed TeX/BibTeX dependency graphs, resolved missing seed DOIs by high-confidence Crossref title matching, and supported bibliography-only early drafts.
