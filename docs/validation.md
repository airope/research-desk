# Research MVP validation — 2026-09-17

136 automated tests passed in 3.14s. Ruff and Django checks pass; no migration drift. A real browser run created an AI search plan, executed three INSPIRE queries and generated a six-publication report through ChatGPT-authenticated Codex. Source drawer and desktop/mobile layouts were inspected. Tests for quotation integrity do not establish scientific correctness or retrieval quality. No paid API or public deployment was used.

# Validation performed — 17 September 2026

## Environment and checks

Native macOS ARM64, Python 3.12.14, Django 5.2.17, PostgreSQL 17.11 on loopback in an isolated temporary cluster. PostgreSQL was downloaded from the official Postgres.app release; there was no usable Docker installation. All Python packages, including optional inference dependencies, are locked in uv.lock.

- **72 pytest tests passed** on real PostgreSQL, including independent transaction/thread races and a hard-crashed worker subprocess.
- Ruff lint and format checks pass; Python modules compile; Django system checks report no issues.
- `makemigrations --check --dry-run`: no changes.
- Generated OpenAPI validates with `--fail-on-warn`: no warnings.
- Offline demo imported 100 records; replay retained 100 records and 100 versions and created no new candidates.
- Actual 1,000-record functional corpus imported into separate `srr_scale` database: 500 Crossref and 500 OpenAlex, no terminal failures.
- Benchmark and frozen MiniLM experiment executed; offline model rerun reproduced nontiming outputs. No live provider calls occur in CI tests.
- PostgreSQL custom-format dump restored into a new database: 100 records, 100 source versions and 2 decision events, matching the demo after accept/withdraw.

## Browser walkthrough

Using the actual local web server and browser: anonymous queue loaded; curator signed in; real *Polynomial Bell Inequalities* pair compared; acceptance recorded; canonical field-level provenance inspected; withdrawal consequences previewed; withdrawal recorded; compensating event and preserved source records verified. After corrections, queue showed 1,405 awaiting-review candidates and ranked exact matches first. Evaluation page displayed test denominators, uncertainty and annotation limitations. Source metadata is escaped as text.

This was a developer-operated workflow, not an independent usability study. Automated access tests cover public write rejection, role separation, CSRF enforcement and untrusted HTML escaping.

## Measured workload

[data/performance-report.json](../data/performance-report.json) records 100 paginated catalogue reads across 10 in-process concurrent readers, 1 warmup request, 1,000 real provider records and 14,075 candidate pairs. p95 was approximately 65.3 ms in this run. Candidate regeneration with existing proposals took 30.75 s and added 0 pairs. This exposes the cost of the straightforward ORM generator and global graph write lock; it is not an optimized bulk reconciliation engine.

The first 200-read workload exceeded the anonymous 120/minute limit and correctly returned 429. The recorded latency run uses 100 requests within that documented public limit, not disabled rate protections. It measures Django middleware/serialization/PostgreSQL within one process, excluding HTTP sockets and web-server overhead. It does **not** establish the PRD's 10,000-record HTTP load target or production capacity.

## Unperformed checks

Docker image/Compose startup and remote GitHub Actions were not executed; their configuration alone is not a passing run. No public deployment, external reviewer/user session, representative manually annotated benchmark, availability test, or OpenSearch reconstruction test is claimed. OpenSearch is not installed.

## Reproduce

```sh
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest -q
uv run python manage.py spectacular --file /tmp/srr-schema.yaml --validate --fail-on-warn
uv run python manage.py benchmark
# Separate test database containing the functional corpus:
PGDATABASE=srr_scale uv run python scripts/measure_catalogue.py
```

Adversarial findings and fixes are in [review.md](review.md). Operational recovery and backup commands are in [operations.md](operations.md).

## Interface redesign — 2026-09-17

All application templates and the shared stylesheet were redesigned following the user request and the official Impeccable Operate/craft-floor guidance. The local skill launcher and its specialist agents were unavailable; direct context reading, browser inspection and an independent existing-agent code review substituted for those integrations. Desktop and 390px narrow-screen queue/evaluation renders were inspected. Source comparison, provenance, imports and evaluation were opened in the browser. The independent review found and corrected action-inaccurate withdrawal wording and hidden year-only metadata. All 72 PostgreSQL tests, Ruff and formatting checks passed. This remains developer verification, not an independent usability study.

## Private user-catalogue milestone — 2026-09-17

The implemented journey is CSV/simulated baseline → bounded live INSPIRE selection → scoped review/correction → CSV catalogue/change report. The original public demonstration remains separate; owner-isolation tests verify private titles do not enter its API. Database migrations for catalogues and frozen audit/source snapshots were applied locally.

Browser walkthrough: created a three-row simulated baseline; imported three incoming cases; merged a duplicate, deferred a conflicting year, added a new publication, and triggered the CSV download. Result: six source entries, four included publications, one merged entry and one deferred entry. Live browser selection ATLAS + journal year2024 + cap3 returned three records and total133 with visible truncation; saved preview remained unconfirmed. Real author lists of roughly3,000 names are retained but collapsed. Desktop1280 and mobile390 renders were inspected; mobile document width375 remained within390 viewport.

Independent review corrected whole-group DOI conflict checks, corrected-field search, unintended correction overrides, repeat-import summaries and intake coverage/provenance handling. These are historical development observations. For reproducible publication checks and their limits, see [publication verification](VERIFICATION.md). This does not establish real-world precision, throughput at the catalogue cap, independent usability or production readiness.
