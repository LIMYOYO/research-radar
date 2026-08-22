---
name: research-radar
description: Run an on-demand, project-aware literature radar from a research folder containing TeX, BibTeX, and a research profile; use when the researcher asks to find new or related papers, inspect citation neighborhoods, distill candidates, obtain one selected paper, create a briefing, or record relevance feedback. Do not use for a generic one-off citation lookup with no project context.
---

# Research Radar

Turn the researcher's current project into a low-noise incremental briefing. The local CLI owns parsing, identifiers, API queries, deduplication, state, and baseline ranking. Codex supplies the qualitative comparison that cannot be reduced to keyword overlap.

Run only in response to the researcher's current request. Never create or edit a
Scheduled task, cron job, or LaunchAgent. Repeated manual invocations remain
incremental because the CLI persists its watermark and seen-paper state.

## Establish the project

Use the directory containing `RESEARCH_PROFILE.md` or `README.md`, a manuscript `.tex`, and one or more `.bib` files. Do not edit those source files unless the user separately asks.

Resolve the CLI in this order: `research-radar` on `PATH`, then the current
repository's `.venv/bin/research-radar`. If neither exists, explain how to
install the package and stop. Use the resolved executable consistently:

```sh
research-radar doctor --project /absolute/project/path
research-radar profile --project /absolute/project/path
```

If the project has not been initialized, run `research-radar init /absolute/project/path`, ask the researcher to replace the generated prompts with substantive project content, and stop before interpreting placeholder text.

## Choose the mode

- For a normal manual update, run `research-radar run --project /absolute/project/path`. Respect a user-supplied date window; otherwise use the configured lookback.
- For a synthesis across prior invocations, run `research-radar weekly --project /absolute/project/path`.
- For offline re-triage after feedback, run `research-radar brief --project /absolute/project/path`.
- For a high-signal DOI without local full text, first run `research-radar access acquire DOI --project /absolute/project/path`. It may automatically archive and export one verified public/OA PDF. Never loop this command over an unreviewed candidate set.
- If `access acquire` returns `authentication-required`, follow [references/browser-access.md](references/browser-access.md) with the connected authorized browser when available.
- If the browser asks for institutional login or Duo, leave the tab as a user handoff and finish the metadata report. Do not request, inspect, enter, or store credentials, Duo responses, cookies, or tokens.
- For a requested paper already downloaded by the user, import it with `research-radar access import` and the correct DOI/route before reading it.

Read the generated Markdown report and focus on `read-now` and `watch` candidates. Do not inflate the result to a fixed count when the report has no high-signal change.

## Deepen the highest-signal entries

For each paper worth presenting, compare it directly with the project's research question, primitives, mechanism, method, assumptions, and contribution delta. Read [references/distillation.md](references/distillation.md) before producing a deep distillation or competitor alert.

Build the evidence packet before deep reading:

```sh
research-radar distill context IDENTITY --project /absolute/project/path
```

If the packet exposes an eligible local PDF but no text file, run its
`full_text_export_command`, then read the page-delimited text. Produce one JSON
object matching the repository's `schemas/distillation.schema.json`, save it
under the private `.research-radar/` directory, and validate/persist it with:

```sh
research-radar distill import /absolute/project/path/.research-radar/distillation.json \
  --project /absolute/project/path
```

Run `research-radar brief --project /absolute/project/path` afterward so the
deep result replaces the shallow baseline card. Do not claim completion of a
deep read if the import is rejected.

Before claiming `full-text`, verify that the acquisition output contains the
requested DOI, a local PDF path, a local text path, page count, checksum, and
`codex_eligible: true` in the ledger. A link label, browser viewer, or provider
availability flag alone is insufficient.

In a briefing, interpret `access_status` only as provider-reported availability.
Use `local_access_status` to decide whether verified local content exists, and
`evidence_level` to decide what claims the card supports. Never rewrite
provider availability as local access.

Treat discovery and evidence as separate:

- `metadata` supports bibliographic claims only.
- `abstract` supports claims stated in the abstract, not unobserved model details or results.
- `full-text` may be claimed only after opening and reading the local PDF or another complete authorized copy in this run.
- A provider saying full text is available does not mean it was read.

Prefer a short, candid update over a fluent but weak summary. Surface adapter failures, unresolved access, and uncertainty. Keep local manuscripts, state, downloaded PDFs, and reports under `.research-radar/`; never add them to Git.

## Capture taste

When the researcher judges a candidate, record the decision rather than only acknowledging it:

```sh
research-radar feedback 'doi:10.xxxx/example' off-topic --project /absolute/project/path --note 'why it missed'
```

Use one of `read-now`, `cite`, `watch`, `known`, `off-topic`, `weak`, or `duplicate`. Preserve the researcher's explanation in `--note` when available. Do not silently modify `RESEARCH_PROFILE.md`; propose profile changes separately.
