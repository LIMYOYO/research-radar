# Research Radar — Access-first Project Plan

- Status: v0.2 local vertical slice implemented; longitudinal validation remains
- Last updated: 2026-08-21
- Current priority: calibrate the complete local workflow on real research projects after passing the access gate and synthetic end-to-end test.

## 0. Access-first sequencing decision

The long-term product goal is unchanged, but the implementation order has
changed. Search and project understanding are not useful if subscription papers
never reach a local file and the system cannot distinguish personal-use access
from permission for Codex reading. The former M3 access milestone is
therefore pulled forward as **Gate A0**, ahead of M0, M1, and M2.

Gate A0 is:

> Given one INFORMS DOI and an authorized University of Toronto user, route the
> user to a permitted full-text source, acquire one article PDF locally, record
> its provenance, and make it available for local analysis under the explicitly
> selected `local-test` or `strict` policy.

Gate A0 was completed on 2026-08-21. Its acceptance checks were:

- one current subscription INFORMS article is acquired through U of T and is
  archived in `.research-radar/papers/` with its AI-use status;
- one open-access INFORMS article completes the same local pipeline;
- DOI, route, timestamp, checksum, page count, technical readability, and
  AI-use eligibility are recorded separately;
- repeated import under the same policy creates neither a duplicate PDF nor a
  duplicate ledger row; a policy change creates an auditable policy record but
  still no duplicate PDF;
- invalid, encrypted, or HTML-disguised-as-PDF files are rejected;
- no credential, cookie, unpublished manuscript, or PDF enters Git history.

The first test matrix is:

| Case | DOI |
| --- | --- |
| Current subscription INFORMS article | `10.1287/mnsc.2025.00819` |
| Open-access INFORMS article | `10.1287/mnsc.2023.00320` |

The execution order is now:

1. **A0:** local PDF intake, validation, provenance, and real U of T browser test;
2. **A1:** access robustness, open-access resolution, and institution adapters;
3. **M0–M2:** research-profile specification, project ingestion, and discovery;
4. **M4–M5:** project-conditioned distillation, ranking, and briefings;
5. **M6–M7:** on-demand Codex skill execution, open-source packaging, and portability.

The detailed one-paper workflow and commands are in
[`docs/access-first.md`](docs/access-first.md).

## 1. Product interpretation

The motivating request is not “search for papers about a keyword.” It is:

> Given my evolving paper, bibliography, and written account of what I am doing differently, continuously find research that is structurally relevant to my project, obtain the strongest legally available evidence, explain the new work in my own analytical frame, and send me only the changes that deserve attention.

The system therefore needs five coupled capabilities:

1. project understanding;
2. graph- and query-based discovery;
3. legal full-text resolution;
4. project-conditioned distillation and ranking;
5. durable state, feedback, and incremental reports.

The working interpretation of “UTD papers” is the UTD24/top-business-journal universe, including subscription outlets such as INFORMS journals. This should be confirmed with the initial users before venue presets are finalized.

## 2. Design decisions already made

| Decision | Rationale |
| --- | --- |
| Create a new `research-radar` repository | The product is much broader than the existing access-router prototype. |
| Keep `paper-access-router` as a technical spike | Browser/library authentication is one adapter, not the product boundary. |
| Local-first MVP | Unpublished TeX, notes, feedback, and downloaded papers may be sensitive. |
| Deterministic CLI plus Codex skill | Parsing, state, and deduplication need tests; distillation and judgment need adaptable instructions. |
| Manual invocation through the skill | The researcher controls timing while persisted state keeps repeated searches incremental. |
| Metadata discovery and full-text access remain separate | Relevance should not disappear merely because access failed. |
| No credential storage or MFA bypass | Institutional authentication remains user- and library-controlled. |
| Markdown reports plus SQLite state | Reports stay readable and reviewable; machine state stays queryable and idempotent. |

## 3. Definition of done

Version 1 is done when two researchers can point the tool at separate real projects and, for four consecutive weeks, receive useful incremental briefings without manual deduplication or repeated setup.

Minimum measurable targets:

- at least 95% of emitted candidates have a stable identifier or an explicit unresolved-identity flag;
- duplicate rate in a briefing is below 2%;
- every candidate shows discovery source, access status, and evidence level;
- every full-text claim is traceable to a local or linked source;
- a failed adapter does not abort the whole run;
- rerunning the same time window is idempotent;
- users rate at least 60% of the top-five weekly candidates as “worth knowing”; this target will be revised after a baseline is measured;
- no credentials, authentication cookies, unpublished source files, or PDFs enter Git history by default.

## 4. Repository shape

Planned structure after the first implementation milestones:

```text
research-radar/
├── README.md
├── PLAN.md
├── pyproject.toml
├── src/research_radar/
│   ├── cli.py
│   ├── project/
│   ├── discovery/
│   ├── access/
│   ├── distill/
│   ├── ranking/
│   ├── reporting/
│   └── state/
├── .agents/skills/research-radar/
│   ├── SKILL.md
│   ├── references/
│   └── scripts/
├── schemas/
├── templates/
├── tests/
│   ├── fixtures/
│   ├── unit/
│   └── integration/
└── examples/
    └── synthetic-project/
```

The first implementation should not create every directory preemptively. Structure is added when a milestone needs it.

## 5. Milestones

### M0 — Specification and evaluation fixture

Goal: turn researcher taste into an inspectable contract before writing adapters.

Deliverables:

- repository README and project plan;
- versioned research-profile schema;
- incremental briefing schema;
- synthetic project fixture with TeX, BibTeX, and known expected outputs;
- one open-source-safe structural fixture derived from real project layouts,
  with every research-specific field rewritten as synthetic content;
- relevance feedback vocabulary: `read-now`, `cite`, `watch`, `known`, `off-topic`, `weak`, `duplicate`;
- initial golden set of relevant, borderline, and irrelevant papers.

Acceptance criteria:

- two researchers can independently fill out the profile without extra explanation;
- the same candidate paper can be distilled into the same required fields;
- private fixture material is excluded from Git;
- at least 20 golden candidates exist for evaluation.

### M1 — Project ingestion and identity layer

Goal: reliably understand what is already in a project.

Deliverables:

- TeX discovery and text extraction;
- BibTeX parsing across multiple files;
- DOI, title, author, year, venue, and preprint identifier normalization;
- duplicate detection for bibliography entries;
- project fingerprint generated from the profile, manuscript, and closest references;
- `research-radar init`, `profile`, and `doctor` commands;
- structured-profile readiness checks so a generic repository README cannot
  silently become the discovery query;
- SQLite schema and migration strategy.

Acceptance criteria:

- parsing does not modify source files;
- at least 95% of DOI-bearing fixtures normalize correctly;
- malformed BibTeX produces actionable diagnostics;
- repeated ingestion produces no duplicate state;
- profile changes are shown for approval before replacing the normalized profile.

### M2 — Multi-lane metadata discovery

Goal: produce a high-recall candidate set without relying on one provider.

Deliverables:

- source-adapter interface;
- initial Crossref and OpenAlex adapters;
- a second citation/semantic adapter selected after coverage testing;
- forward citation, reference-neighborhood, keyword, author, and venue queries;
- UTD24 and INFORMS venue presets as configuration, not hard-coded ranking truth;
- time-window and `since last-success` semantics;
- cross-source deduplication and provenance retention;
- rate-limit, retry, and partial-failure handling.
- per-provider success watermarks so a partial run retries only the sources
  whose date-bounded work did not complete;

Acceptance criteria:

- at least two sources run in one command;
- a source outage is visible but nonfatal;
- the golden set establishes a documented recall baseline;
- rerunning a window does not create new duplicate candidates;
- every candidate preserves all discovery lanes that found it.

### M3 — Legal access resolution (pulled forward as Gate A0)

Goal: turn discovered metadata into the strongest authorized evidence available.

Deliverables:

- access-result schema: `full-text`, `accepted-manuscript`, `abstract`, `metadata-only`, `request`;
- open-access resolver;
- LibKey resolver;
- U of T OpenAthens/EBSCO handoff for individual user-initiated requests;
- optional integration or code reuse from `paper-access-router`;
- PDF acquisition ledger with source, timestamp, license/access route, PDF/text
  checksums, and DOI/title identity verification;
- separate technical-readability and AI-use-permission states;
- explicit image-only visual-review state with all-page confirmation;
- safe download limits and explicit manual-authentication boundary.

Acceptance criteria:

- no credentials or browser cookies are written by the tool;
- a metadata-only paper remains reportable;
- the same PDF is not downloaded twice;
- current and historical INFORMS test papers have documented outcomes;
- the workflow clearly pauses when user authentication is required;
- bulk-download behavior is absent.

### M4 — Project-conditioned distillation and ranking

Goal: explain why a paper matters to this project, not merely what it says.

Deliverables:

- typed distillation schema;
- separate prompts/instructions for analytical, empirical, experimental, and methods papers;
- evidence-level labels for full text, abstract, or metadata inference;
- relationship taxonomy: `supports`, `contradicts`, `extends`, `competes`, `method-lead`, `background`;
- ranking features for topical fit, structural fit, novelty, recency, venue prior, citation relation, and priority risk;
- explicit reason trace for each ranking;
- calibration set reviewed by initial users.

Acceptance criteria:

- no abstract-only candidate is described as though full text was read;
- each top candidate names at least one concrete relationship to the project profile;
- scores are accompanied by reasons and can be overridden;
- rankings outperform a title/abstract keyword baseline on the golden set;
- unsupported claims fail validation or are labeled as inference.

### M5 — Incremental briefing and feedback loop

Goal: make the output fast to consume and better over time.

Deliverables:

- Markdown briefing generator;
- append-only run manifest with search window and adapter status;
- top-signal summary plus detailed candidate cards;
- feedback capture from Markdown or CLI;
- suppression rules for known, duplicate, or repeatedly rejected clusters;
- watchlist for important authors, papers, and unresolved access;
- weekly synthesis in addition to the per-run delta.

Acceptance criteria:

- an incremental report contains only unseen or materially updated items;
- user feedback affects the next ranking without erasing audit history;
- report generation is deterministic from stored candidate/distillation records;
- no-change runs produce a concise “no high-signal change” report rather than noise;
- all filtered candidates remain auditable.

### M6 — Codex skill and manual execution

Goal: make the validated workflow natural to run and repeat.

Deliverables:

- repository-scoped `.agents/skills/research-radar/SKILL.md`;
- references for profile, evidence, ranking, and report standards;
- deterministic scripts invoked by the skill;
- manual end-to-end skill tests;
- global-skill installation and invocation guide;
- run mode that defaults to read-only project ingestion and writes only inside `.research-radar/`;
- concise summary behavior for successful, empty, and failed invocations.

Acceptance criteria:

- explicit and implicit skill invocations choose the correct workflow;
- a repeated manual run is idempotent and resumes from the last successful watermark;
- the skill can run against a local Git project while preserving local privacy;
- three consecutive invocations complete without duplicate reports;
- failures include a clear recovery action.

### M7 — Sharing, packaging, and portability

Goal: let other researchers install the workflow without inheriting U of T-specific assumptions.

Deliverables:

- installation and onboarding documentation;
- pluggable institution and venue configuration;
- sample profiles for analytical OM, empirical business research, and adjacent fields;
- privacy and responsible-access documentation;
- plugin packaging evaluation for skill plus connectors;
- public issue templates and contribution guide;
- semantic versioning and changelog.

Acceptance criteria:

- a non-U of T user can run metadata-only and open-access workflows;
- institution-specific routes are optional adapters;
- a fresh installation can produce a synthetic-project report from documented steps;
- public artifacts contain no private paper content or credentials;
- two external users complete onboarding and report friction points.

## 6. Evaluation plan

### Offline evaluation

For each fixture project, maintain:

- known relevant papers;
- hard negatives with overlapping terminology;
- closest competitors;
- papers relevant only by method or mechanism;
- duplicates across preprint and published versions;
- candidates with full text, abstract only, and no abstract.

Measure:

- discovery recall by lane and source;
- precision at 5 and 10;
- duplicate rate;
- identifier-resolution rate;
- access-resolution success by route;
- evidence-label accuracy;
- ranking agreement with researcher judgments;
- run cost, latency, and adapter failure rate.

### Online evaluation

Initial users mark each surfaced candidate and optionally explain why. Weekly review asks:

- Did the radar surface anything the researcher would otherwise have missed?
- Did it miss a paper the researcher found elsewhere?
- Was the relationship-to-project explanation correct?
- Did any summary overstate the available evidence?
- Which rejection reasons should become profile exclusions?

Feedback is project-specific by default; cross-project learning requires an explicit design decision and consent.

## 7. Risks and mitigations

| Risk | Consequence | Planned mitigation |
| --- | --- | --- |
| Citation providers disagree or lag | False confidence in completeness | Multi-source provenance and visible coverage gaps. |
| Google Scholar automation has not been evaluated for acceptable use | Brittle or noncompliant dependency | Do not make Scholar automation an MVP dependency; evaluate terms separately. |
| Publisher and library authentication changes | Broken full-text routes | Adapter boundary, manual fallback, and integration tests. |
| Institutional authentication expires | A requested full text cannot be fetched | Complete the metadata run, queue the access request, never fake success. |
| Generic LLM summaries sound convincing | Poor research decisions | Typed evidence labels, source links, and evaluation fixtures. |
| Project profile is vague | High-noise recommendations | Require closest-literature and exclusion sections; support iterative review. |
| New-paper novelty is confused with relevance | Trendy but useless briefing | Separate novelty, structural fit, and decision-value scores. |
| Private manuscripts leak through logs or Git | Serious confidentiality failure | Local-first storage, conservative `.gitignore`, redacted fixtures, secret scans. |
| Venue prestige dominates ranking | Missed relevant working papers | Venue is a configurable prior, never a hard filter. |
| Automated reports become another inbox | Tool abandonment | Top-N limits, empty-day summaries, and feedback-based suppression. |

## 8. Remaining calibration decisions

The implementation now has safe defaults. These choices should be calibrated
with the first two real users rather than guessed from the synthetic fixture:

1. Does the shared venue preset need exactly UTD24 or a broader business-journal set?
2. What precision-at-five target is realistic for analytical versus empirical projects?
3. Which private project can supply the first 20-paper judged golden set?
4. When should a `watch` item escalate between invocations rather than wait for a weekly review?
5. How should collaborators share project profiles and feedback without sharing licensed PDFs?

## 9. Calibration next actions

The code-complete local beta now needs longitudinal evidence:

1. Select the first private project and fill its explicit `RESEARCH_PROFILE.md`.
2. Judge at least 20 candidate papers, including hard negatives and competitors.
3. Invoke the skill during normal work for one week, then tune queries, exclusions, and thresholds.
4. Onboard a second researcher and record installation or interpretation friction.

## 10. Implementation snapshot — 2026-08-21

Implemented and tested:

- Gate A0 on one subscription and one open-access INFORMS article;
- local-test and strict analysis policies with provenance ledger;
- bounded one-paper automatic acquisition with browser-authentication fallback;
- page-delimited PDF text export for Codex;
- research-profile, candidate, and briefing schemas;
- TeX/BibTeX ingestion, DOI normalization, project fingerprinting, and SQLite state;
- Crossref keyword discovery plus OpenAlex forward-citation, related-work, and keyword lanes;
- Semantic Scholar forward-citation and backward reference-neighborhood lanes;
- explicit author and venue watches with INFORMS and UTD24 presets;
- cross-source identity merge, caching, retry, and adapter failure isolation;
- explainable project-conditioned ranking with novelty and priority-risk traces;
- typed, validated, append-only deep distillations that hydrate later reports;
- idempotent incremental and weekly Markdown briefings and feedback-based suppression;
- repository-scoped `$research-radar` skill;
- a live synthetic-project run against all three metadata providers;
- a 20-candidate synthetic golden set with an executable precision/recall and keyword-baseline evaluation;
- read-only live discovery smoke tests on one mature and one pre-citation private project.

The remaining product definition-of-done checks require external participation
and elapsed use: two real researchers, four weeks of runs, and a reviewed
20-paper-per-project golden set. The completion audit distinguishes those
longitudinal checks from locally verified engineering behavior; neither should
be fabricated from the synthetic demo.

## 11. Documentation basis

The planned Codex integration follows current official guidance:

- skills package instructions, resources, and optional scripts for reusable workflows;
- repository skills can live under `.agents/skills` and be checked into the project;
- manual skill invocations keep the researcher in control of timing and interactive access.

References:

- [OpenAI — Build skills](https://learn.chatgpt.com/codex/skills)
