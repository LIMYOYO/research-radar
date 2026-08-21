---
name: research-radar
description: Run a project-aware literature radar from a research folder containing TeX, BibTeX, and a research profile; use for recurring paper discovery, citation-neighborhood monitoring, evidence-aware distillation, briefings, or relevance feedback. Do not use for a generic one-off citation lookup with no project context.
---

# Research Radar

Turn the researcher's current project into a low-noise incremental briefing. The local CLI owns parsing, identifiers, API queries, deduplication, state, and baseline ranking. Codex supplies the qualitative comparison that cannot be reduced to keyword overlap.

## Establish the project

Use the directory containing `RESEARCH_PROFILE.md` or `README.md`, a manuscript `.tex`, and one or more `.bib` files. Do not edit those source files unless the user separately asks.

Run the repository's CLI through its virtual environment when present:

```sh
.venv/bin/research-radar doctor --project /absolute/project/path
.venv/bin/research-radar profile --project /absolute/project/path
```

If the project has not been initialized, run `research-radar init /absolute/project/path`, ask the researcher to replace the generated prompts with substantive project content, and stop before interpreting placeholder text.

## Choose the mode

- For a normal update, run `research-radar run --project /absolute/project/path`. Respect a user-supplied date window; otherwise use the configured lookback.
- For offline re-triage after feedback, run `research-radar brief --project /absolute/project/path`.
- For a requested paper already downloaded by the user, import it with `research-radar access import` and the correct DOI/route before reading it.
- For access troubleshooting, follow the documented one-paper route in `docs/access-first.md`. Pause for interactive institutional authentication rather than asking for or recording credentials.

Read the generated Markdown report and focus on `read-now` and `watch` candidates. Do not inflate the result to a fixed count when the report has no high-signal change.

## Deepen the highest-signal entries

For each paper worth presenting, compare it directly with the project's research question, primitives, mechanism, method, assumptions, and contribution delta. Read [references/distillation.md](references/distillation.md) before producing a deep distillation or competitor alert.

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
