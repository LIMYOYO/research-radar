# Access-first workflow

The first Research Radar milestone is deliberately narrow:

> Given one INFORMS DOI and an authorized University of Toronto user, obtain one
> article PDF through a permitted route, archive it locally, and prove that Codex
> can read it.

Authentication and the final single-article download remain in the user's
browser. Research Radar never receives UTORid credentials, Duo responses,
cookies, or a reusable download token.

## Install the local CLI

From this repository:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
```

## One-paper INFORMS workflow

1. Start or refresh the U of T Business Source Premier session:

   ```sh
   .venv/bin/research-radar access session
   ```

2. Complete UTORid and Duo in the browser if requested.
3. Open the article through LibKey:

   ```sh
   .venv/bin/research-radar access open 10.1287/mnsc.2025.00819
   ```

4. Use the offered PDF/full-text link and download this single article.
5. Import the downloaded file into the research project:

   ```sh
   .venv/bin/research-radar access import ~/Downloads/article.pdf \
     --doi 10.1287/mnsc.2025.00819 \
     --route uoft-ebsco \
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

## Verify Codex readability

```sh
.venv/bin/research-radar access verify \
  /path/to/my-research-project/.research-radar/papers/10.1287_mnsc.2025.00819.pdf
```

Success requires a structurally valid, unencrypted PDF with extractable text.
An image-only PDF can be archived with `--allow-image-only`, but it is explicitly
marked as not text-readable and requires OCR or visual reading later.

## Acceptance test matrix

| Case | DOI | Expected result |
| --- | --- | --- |
| Current subscription INFORMS article | `10.1287/mnsc.2025.00819` | U of T/LibKey route yields an importable PDF |
| Open-access INFORMS article | `10.1287/mnsc.2023.00320` | OA route yields an importable PDF without institutional authentication |
| Repeated import | Either DOI | No duplicate PDF or ledger entry |
| Missing full text | Any DOI | Route failure is reported; no fake PDF record is written |
| Encrypted or invalid file | Any DOI | Import fails with an actionable error |

## Security and licensing boundary

- Access is user-initiated and article-by-article.
- No MFA bypass, credential storage, cookie extraction, or bulk download.
- The ledger records the route and file checksum, not authentication data.
- Licensed PDFs remain local and are never committed or redistributed by default.
