# Access-first workflow

The first Research Radar milestone is deliberately narrow:

> Given one INFORMS DOI and an authorized University of Toronto user, obtain one
> article PDF through a permitted route, archive it locally, and make it
> available for private local analysis under the selected analysis policy.

Interactive authentication remains in the user's browser. Once that session is
authorized, the skill may click the final single-article download control.
Research Radar never receives UTORid credentials, Duo responses, cookies, or a
reusable download token.

## Install the local CLI

From this repository:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
```

## One-paper INFORMS workflow

1. Attempt one bounded automatic acquisition:

   ```sh
   .venv/bin/research-radar access acquire 10.1287/mnsc.2025.00819 \
     --project /path/to/my-research-project
   ```

   If this returns `acquired` or `existing`, the verified PDF and page-delimited
   text are already local. If it returns `authentication-required`, continue
   with the reported `handoff_url`. Use `access resolve` when only inspecting
   routes is desired.

2. Start or refresh the U of T Business Source Premier session:

   ```sh
   .venv/bin/research-radar access session
   ```

3. Complete UTORid and Duo in the browser if requested.
4. Open the article through LibKey:

   ```sh
   .venv/bin/research-radar access open 10.1287/mnsc.2025.00819
   ```

5. Use the offered PDF/full-text link and download this single article. In the
   EBSCO PDF viewer, the toolbar download button opens a modal; keep PDF selected
   and confirm Download.
6. Import the downloaded file into the research project:

   ```sh
   .venv/bin/research-radar access import ~/Downloads/article.pdf \
     --doi 10.1287/mnsc.2025.00819 \
     --route uoft-ebsco \
     --ai-use-status unknown \
     --project /path/to/my-research-project
   ```

The PDF is copied to:

```text
/path/to/my-research-project/.research-radar/papers/10.1287_mnsc.2025.00819.pdf
```

The acquisition ledger is written to:

```text
/path/to/my-research-project/.research-radar/access-ledger.jsonl
```

Both are private local state and are ignored by Git when the recommended
project `.gitignore` is used.

## Verify technical readability

```sh
.venv/bin/research-radar access verify \
  /path/to/my-research-project/.research-radar/papers/10.1287_mnsc.2025.00819.pdf
```

Success requires a structurally valid, unencrypted PDF with extractable text
whose DOI or full normalized title matches the requested candidate. A readable
but mismatched PDF is rejected before it reaches the ledger. Exported text has a
sidecar binding its own checksum to the archived PDF checksum.

An image-only PDF can be archived with `--allow-image-only`, but it remains
`pending-visual` and ineligible for full-text claims. After a PDF-capable reader
visibly verifies the DOI/title and reviews every page, record the review:

```sh
.venv/bin/research-radar access confirm-visual 10.1287/example \
  --identity visual-doi-match \
  --pages-reviewed 12 \
  --note 'DOI visible on page 1; all 12 pages reviewed' \
  --project /path/to/my-research-project
```

Technical readability and source terms are recorded as different fields.
During private prototype evaluation, `--analysis-policy local-test` is the
default and source terms are advisory rather than blocking. Use
`--analysis-policy strict` to skip extraction when `--ai-use-status prohibited`;
the record will then show `text_extraction_performed: false`.

For a clearly licensed open-access paper, record the license explicitly:

```sh
.venv/bin/research-radar access import ~/Downloads/open-paper.pdf \
  --doi 10.1287/mnsc.2023.00320 \
  --route uoft-ebsco \
  --ai-use-status allowed \
  --license-name "CC BY 4.0" \
  --license-url https://creativecommons.org/licenses/by/4.0/ \
  --project /path/to/my-research-project
```

## Acceptance test matrix

| Case | DOI | Expected result |
| --- | --- | --- |
| Current subscription INFORMS article | `10.1287/mnsc.2025.00819` | U of T/LibKey route yields an importable personal-use PDF; the prototype records terms but `local-test` does not block local analysis |
| Open-access INFORMS article | `10.1287/mnsc.2023.00320` | OA route yields an importable PDF without institutional authentication |
| Repeated import under the same policy | Either DOI | No duplicate PDF or ledger entry; changing policy may append one audit record without copying the PDF |
| Missing full text | Any DOI | Route failure is reported; no fake PDF record is written |
| Encrypted or invalid file | Any DOI | Import fails with an actionable error |
| Valid PDF for the wrong article | Any DOI | DOI/title identity check rejects it before archival |
| Image-only PDF | Any DOI | Remains `pending-visual` until an explicit all-page visual confirmation |
| Public URL returns HTML/403 | Any DOI | No ledger is written; the result is `authentication-required` with a LibKey handoff |
| Oversized response | Any DOI | Streaming stops at the configured `--max-mb` limit |

## Security and licensing boundary

- Access is user-initiated and article-by-article.
- No MFA bypass, credential storage, cookie extraction, or bulk download.
- The ledger records the route and file checksum, not authentication data.
- AI eligibility is recorded separately from technical PDF readability.
- Licensed PDFs remain local and are never committed or redistributed by default.
