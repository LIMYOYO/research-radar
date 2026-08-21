# Plugin packaging evaluation

## Decision

Version 0.2 ships as a normal Python package plus a repository-scoped Codex
skill. A Codex plugin is not required for the first public release.

The deterministic CLI already owns parsing, provider requests, state,
deduplication, access provenance, and report generation. The skill adds the
project-specific qualitative judgment and calls that CLI from the checked-out
repository. This arrangement has three useful properties:

- it works in any terminal and remains testable without Codex;
- private manuscripts, PDFs, and state stay in the research project;
- contributors can inspect and change the exact prompt and evidence standard.

## When a plugin becomes justified

Re-evaluate plugin packaging when Research Radar needs to distribute one or
more capabilities that a repository skill cannot supply cleanly:

1. a maintained institution connector with its own MCP server;
2. a graphical triage surface for feedback and access queues;
3. centrally managed installation and updates for nontechnical users;
4. an app connection whose permissions must be declared independently of the
   Python package.

At that point, the plugin should wrap the existing CLI rather than duplicate
its state or ranking logic. Institution adapters must remain optional, and the
plugin manifest must not imply access to credentials, browser cookies, local
PDFs, or unpublished manuscripts beyond what the user explicitly selects.

## Public-release packaging checklist

- publish the Python package and repository skill from the same tagged commit;
- retain the MIT license, changelog, schemas, examples, and synthetic tests;
- keep `.research-radar/`, PDFs, extracted text, and generated reports ignored;
- document optional environment variables without committing their values;
- create a plugin only after one of the distribution needs above is observed in
  onboarding, not merely to add another package format.
