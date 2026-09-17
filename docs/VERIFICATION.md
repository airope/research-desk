# Publication verification

## Reproduce locally

Use a disposable PostgreSQL database and the frozen dependencies. Never point the test run at a personal or production database.

```sh
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest -q
# Opt-in host sandbox and slow-response tests (macOS or supported Linux host):
RUN_PDF_SANDBOX_TEST=1 uv run pytest tests/test_research_fulltext.py -q
```

The publication copy was installed independently and tested with Python 3.12.13 and an isolated PostgreSQL 17 cluster. The full local run including opt-in PDF/HTTP host tests passed **424 tests**, with **one Elasticsearch integration test skipped** because no disposable search service was configured for that run. Ruff, Django checks, migrations and OpenAPI validation were also exercised. These are bounded developer checks, not a production security certification.

The installed Python distributions were checked with pip-audit; no known vulnerabilities were reported in that run. Secret scanning used Gitleaks with four reviewed, path-and-value-specific checksum exclusions. These checks cannot guarantee that all vulnerabilities or private information are absent.

## Browser evidence

Actual Chrome sessions used fresh browser contexts, an isolated database and a disposable account with an unusable password. The browser was restricted to the local application; no model was invoked.

Verified: anonymous landing and protected catalogue route, authenticated session, simulated CSV preview/import, incoming example selection, source comparison, adding a record, CSV download, research question validation, creation of a draft with no generated content, and a narrow mobile overflow check. No uncaught JavaScript errors were observed in those flows. This does **not** verify password login, every accessibility path, a completed model-generated report or exhaustive multi-user behavior.

The README screenshots are unmodified captures of that application. Catalogue records are explicitly simulated. No private documents, original runtime database, provider credentials or pre-generated AI reports were used.

## Network and optional features

A single live, bounded INSPIRE metadata search returned HTTP 200 through the hardened transport. An abstract without an allowed source was omitted. This verifies that request path, not comprehensive upstream availability or research quality.

Paid model APIs and personal Codex were not exercised in this publication run. Model behavior is covered by contract tests, not a claim of live validation for every provider. Optional Codex remains disabled and experimental. PDF isolation is OS-dependent and must be checked on each deployment host; local macOS evidence does not prove Docker/Linux namespace availability.

## CI and release boundary

[GitHub Actions](https://github.com/airope/research-desk/actions) is the authority for the result on each exact commit. The workflow tests PostgreSQL-backed behavior, a disposable Elasticsearch service, production configuration, schema validation and an actual Docker Compose build/start/offline demo. Read its result rather than treating the workflow file itself as proof of success.

Only source, public or simulated fixtures, documentation and screenshots are published. No prebuilt image, database, model weights or hosted application is included. Older benchmark/audit documents retain their historical scope and do not replace the current checks or the [security policy](../SECURITY.md).
