# Contributing

Research Radar welcomes focused changes to project parsing, source adapters,
identity resolution, ranking evaluation, access routing, and report usability.

1. Create a virtual environment and install the package with `pip install -e .`.
2. Add or update a synthetic fixture; never commit private manuscripts, cookies,
   downloaded papers, or institutional credentials.
3. Run `python -m unittest discover -s tests -v` and `python -m compileall -q src tests`.
4. Explain observable behavior and evidence in the pull request.

New discovery adapters must retain provenance, tolerate partial failure, and use
mocked unit tests rather than depending only on live network results. New
distillation fields must preserve the distinction between metadata, abstract,
and actually-read full text.
