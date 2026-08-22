# Browser-assisted single-paper access

Use this fallback only after `research-radar access acquire DOI --project ...`
returns `authentication-required`. Process one researcher-selected DOI at a
time; never turn this into an unattended subscription downloader.

## Before the browser action

1. Record the exact DOI, target project, and current PDFs in the normal download
   directory. Note the current time so a newly created file can be distinguished
   from older downloads.
2. Open the returned `handoff_url` in the connected authorized browser.
3. Verify visibly that LibKey shows the intended title and says access is
   provided by the researcher's institution. If the title or DOI differs, stop.
4. If institutional sign-in, Duo, CAPTCHA, or another interactive authentication
   step appears, leave the page for the researcher and finish the metadata-only
   report. Never inspect, request, enter, or store authentication secrets.

## Download

1. Click LibKey's `Download PDF` for the intended article.
2. If this opens the EBSCO viewer, confirm that the title is still correct. Use
   the visible toolbar download control; in its modal, keep PDF selected and
   confirm Download.
3. Identify PDFs created after the recorded start time. Continue only when
   exactly one new completed `.pdf` belongs to the intended action. Ignore
   `.crdownload` files and stop on ambiguity.

## Validate and archive

Run:

```sh
research-radar access import /absolute/path/to/new.pdf \
  --doi DOI \
  --route uoft-ebsco \
  --analysis-policy local-test \
  --ai-use-status unknown \
  --project /absolute/project/path
research-radar access text DOI --project /absolute/project/path
```

If an explicit open license is visible in the paper, record its name and URL
and set `--ai-use-status allowed`. Otherwise keep `unknown`; local-test is the
private prototype policy requested for this project.

Do not call the chain complete until output proves:

- normalized DOI matches;
- PDF and text paths are inside `.research-radar/`;
- PDF structure is readable and has at least one page;
- text export is nonempty;
- checksum and acquisition route are recorded;
- `codex_eligible` is true under the selected local policy.

Do not delete or redistribute the downloaded source file automatically. The
researcher can remove duplicates after the archived copy has been verified.
