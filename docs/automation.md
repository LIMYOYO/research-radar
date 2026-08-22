# Daily Research Radar with ChatGPT Scheduled tasks

Research Radar is designed to run once per day from the ChatGPT desktop app.
OpenAI's current Scheduled tasks documentation says that desktop tasks can work
with local projects, while the computer must remain on and the app running when
local files are needed. Task creation and run management happen in ChatGPT web
or the desktop app, not in Codex CLI or the IDE extension.

Official reference: [OpenAI — Scheduled tasks](https://learn.chatgpt.com/docs/automations)

## Before scheduling

From the target research project, complete one manual run:

```sh
/absolute/path/to/research-radar/.venv/bin/research-radar doctor --project .
/absolute/path/to/research-radar/.venv/bin/research-radar run --project .
```

`doctor` must report `profile-structure: complete`. If the project already has
an ordinary software `README.md`, `research-radar init` creates a separate
`RESEARCH_PROFILE.md` without modifying that README. Fill every required
section before scheduling; otherwise discovery deliberately stops.

Fix any profile, BibTeX, or source diagnostics. Review the first report and add
feedback for obvious noise. The schedule should reproduce a trusted manual run,
not serve as the first integration test.

## Recommended task settings

- Cadence: daily, once per day.
- Time zone: the researcher's local time zone.
- Project mode: local project directory, not an isolated Git worktree.
- Suggested time: 08:00, when the machine is normally awake.
- Skill: `$research-radar` from this repository.

The local-project choice is important: `.research-radar/state.sqlite`, licensed
PDFs, extracted text, and prior reports are private ignored files that do not
exist in a fresh worktree.

## Task prompt

Replace the two absolute paths before saving:

```text
Use $research-radar in /absolute/path/to/my-research-project.

Run the daily incremental radar with the CLI at
/absolute/path/to/research-radar/.venv/bin/research-radar. Read the generated
briefing. Report only read-now and watch signals; do not fill a quota. For the
highest-signal paper, compare its question, primitives, mechanism, method,
assumptions, and contribution with RESEARCH_PROFILE.md. Keep metadata,
abstract, and full-text evidence labels distinct. Run `access acquire DOI` for
at most the highest-signal unresolved paper. If it returns an institutional
handoff and an authorized browser session is available, use the one-paper
LibKey/EBSCO download flow, import the downloaded PDF, and run `access text DOI`
before claiming full-text evidence. Then write and persist a JSON result through
`distill import`. If institutional authentication or Duo is required,
leave the paper as an access request and finish the metadata report. Do not edit
paper.tex or references.bib. End with the report path and any recovery action.
```

## Operational behavior

The metadata run does not require Duo. A background run should not wait on an
interactive login: it records the paper and its access status, then finishes.
When the researcher next opens the app, they can acquire a high-value PDF using
the authorized browser session and import it. A subsequent run can then deepen
that paper from local full text.

Review the first few scheduled runs and tune `top_n`, keywords, venues, and
exclusions in `.research-radar/config.yaml`. Pause the task if the selected
project is moved or the virtual environment is removed.

Run `research-radar weekly --project .` in a separate weekly task if a synthesis
of recurring concepts, relationships, venues, and unresolved full-text items is
useful. `SEMANTIC_SCHOLAR_API_KEY` is optional; if supplied through the task
environment it raises API reliability, and the tool never persists it.
