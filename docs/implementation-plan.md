# Implementation plan and acceptance map

The initial repository is empty. All paths below are new; no existing line references apply.

1. `srr/settings.py`, `pyproject.toml`, `uv.lock`, `compose.yaml`, `Dockerfile`: pinned Django 5.2/Python/PostgreSQL environment, native session authentication, bounded read APIs, worker and CI (F5).
2. `records/models.py`, `normalization.py`, `matching.py`, `services.py`, migrations: retained source versions, provenance projections, ordered candidates, reproducible evidence, transactional reversible human decisions and graph conflict checks (F2–F4).
3. `records/ingestion.py`, `connectors.py`, management commands: bounded provider imports and offline fixtures, durable checkpoints, expiring fenced leases, visible failures and retry (F1).
4. `records/api.py`, `views.py`, `urls.py`, templates/static: English review queue, comparison, catalogue/provenance, withdrawal preview, import diagnostics, evaluation and generated OpenAPI (F1–F4).
5. `data/`, `scripts/`, `records/evaluation.py`: licensed minimal real snapshots and explicitly synthetic cases, immutable group split, independent candidate/decision metrics, errors and uncertainty, DOI-only and lexical baselines (F5).
6. `tests/`, `.github/workflows/ci.yml`: PostgreSQL constraints, concurrent decisions, stale revisions, graph splits/redundant links, import replay/crash, HTTP failures, authentication/CSRF, end-to-end browser validation.
7. `docs/architecture.md`, `docs/decisions.md`, `docs/operations.md`, README and PROGRESS: implementation evidence, competency mapping and explicit extension decisions. Evaluate embeddings once the foundation is stable; OpenSearch, React, Airflow, MCP must receive explicit decisions based on observed needs.

Constraints: local work only, no expenses/publication or personal application documents. No AI accuracy claims or automatic associations before sufficient independent evaluation. PRD kept unchanged in `docs/PRD-reference.md`; deviations recorded in decisions.

Team ownership: domain agent owns models/services/matching/normalization and their tests; ingestion agent owns connectors/worker fixtures and connector tests; interface agent owns API/views/templates and access tests; root integrates, handles environment, benchmark, documentation and verification.
