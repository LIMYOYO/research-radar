# INFORMS access validation — 2026-08-21

This record contains no account name, UTORid, cookie, token, or Duo response.

## Environment

- Institution: University of Toronto
- Database: Business Source Premier
- Institutional route: U of T OpenAthens to EBSCO
- Browser helper: LibKey Nomad
- Test mode: individual, user-authorized article requests

## Subscription test

- DOI: `10.1287/mnsc.2025.00819`
- Result: found as one exact EBSCO record in Business Source Premier
- Full text: HTML and PDF access were present
- Local PDF download: succeeded
- File size: 3,409,659 bytes
- Pages: 22
- SHA-256: `a5865024b798acd97ce7a2f515cc7c89210027230035007097b3f45830eac4f4`
- Access status: `full-text`
- AI-use status: `prohibited` (advisory in local-test mode)

The EBSCO record displayed terms permitting individual printing, downloading,
or emailing while prohibiting use with artificial-intelligence or
machine-learning tools. The PDF is therefore archived for permitted personal
use. The private prototype records this status but, in `local-test` mode, does
not use it as a technical blocker. A public deployment can select `strict` mode.

## Open-access control

- DOI: `10.1287/mnsc.2023.00320`
- Result: LibKey Nomad routed the article through the authenticated EBSCO viewer
- Local PDF download: succeeded
- File size: 3,675,962 bytes
- Pages: 22
- Extracted text characters: 115,324
- SHA-256: `7c5e4b37d7863d8ee2d993565220d2be5abfe5f1e0094b2b37837b374fd4b15e`
- License: CC BY 4.0
- AI-use status: `allowed`
- Codex eligibility: `true`

The first page was rendered locally and visually checked. It was legible,
complete, and displayed the CC BY 4.0 open-access statement.

## Observed failure mode

The publisher PDF URL returned HTTP 403 to a command-line client, and a direct
media-link attempt initially saved an HTML redirect page rather than a PDF.
The authenticated browser viewer produced the valid PDF. This confirms that
the production workflow must validate MIME/content and PDF structure after
every download rather than trusting a filename or link label.

## Gate result

- U of T institutional access to an individual current INFORMS article: passed
- Browser-to-local PDF acquisition: passed
- Local validation, stable naming, checksum, and ledger: passed
- OA PDF available to Codex under an explicit license: passed
- Subscription EBSCO PDF technically available to the local prototype: passed

## Revalidated browser-assisted chain

The complete chain was repeated after adding `access acquire`:

1. the command-line publisher candidate returned HTTP 403 and correctly
   returned `authentication-required` with no ledger entry;
2. LibKey recognized University of Toronto and exposed `Download PDF`;
3. the existing authenticated EBSCO session opened all 22 pages without another
   Duo prompt;
4. the EBSCO download modal produced a 3,675,962-byte PDF;
5. import reproduced SHA-256
   `7c5e4b37d7863d8ee2d993565220d2be5abfe5f1e0094b2b37837b374fd4b15e`;
6. text export produced 115,732 page-delimited characters and marked the local
   copy Codex-eligible.

This establishes a deterministic fallback: automatic public download when
possible, authorized browser handoff when required, and the same local
validation/import/text pipeline in both cases.

Alternate-copy resolution remains useful because OpenAlex did not correctly
identify the OA status of either recent INFORMS test record.
