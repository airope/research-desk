# Contributing to Research Desk

Bug reports, documentation improvements and focused patches are welcome. Discuss substantial changes in a GitHub issue before building a new subsystem. Report suspected vulnerabilities using [SECURITY.md](SECURITY.md), not a public exploit report.

## Development setup

Follow the native setup in [README.md](README.md). Use an isolated PostgreSQL database and a role with test-database creation permission. Do not point tests or fixture-generation scripts at a database containing valuable research work. Install the locked development dependencies with `uv sync --frozen`.

Before submitting a patch, run:

```sh
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
```

Report the commands you actually ran and any skipped checks. Database tests, live provider tests, container startup and scientific-quality evaluation are different kinds of evidence. Do not describe mocked calls as live validation. Optional Elasticsearch and embedding experiments are documented separately.

## Patch expectations

- Keep changes small and explain the user-visible behavior and limitations.
- Add regression tests for fixes, including owner isolation and failure paths where relevant.
- Preserve original source evidence, provenance, human decisions and version history. Use migrations for schema changes; do not silently rewrite retained sources.
- Keep model/provider choice explicit. Do not introduce hidden cloud fallbacks, paid calls in default tests, arbitrary model-selected URLs or execution of generated code.
- Treat provider metadata, PDFs and model output as untrusted input. Preserve bounds, validation, cancellation fences and endpoint restrictions.
- Update relevant user documentation when behavior or configuration changes.
- Use synthetic fixtures or minimal redistributable public metadata. Include source, acquisition method and applicable terms; label weak and synthetic benchmark labels accurately.
- Never include `.env`, tokens, database dumps, private dossiers, account details or local model caches in a patch. Redact logs and screenshots before sharing.

## Rights and attribution

Submit only material you have the right to contribute. Contributions to project code and original documentation are made under the repository's existing MIT license. Preserve upstream copyright/license notices and clearly identify any third-party material; a citation alone does not grant redistribution rights. See [third-party notices](docs/third-party-notices.md).

AI-assisted changes need the same review, tests and provenance scrutiny as any other contribution. The contributor remains responsible for correctness and rights. Do not submit confidential prompts, copied proprietary implementations, fabricated test results or invented citations.
