# Decisions and material differences from PRD v1.0

## ADR 1 — LTS monolith and local PostgreSQL

Use Django 5.2 LTS, Python 3.12, PostgreSQL 17 and locked Python dependencies. Docker Compose describes local web, worker and database. The execution host lacks Docker; validate with an isolated native PostgreSQL 17.11 and document Compose as not executed here. No SQLite substitution for transaction tests.

## ADR 2 — No automatic association

The available benchmark has constructed cases and DOI-derived weak labels, with no independent manual annotation. Consequently every proposal requires human review. Experimental baseline precision is not production automatic precision. This follows the PRD's explicit abstention condition rather than claiming its 99% target.

## ADR 3 — Graph locking and stable history

Use a PostgreSQL transaction advisory lock for graph mutations, with row locking and expected revisions for review. This avoids silent transitive races, at the cost of serialized writes. Affected components are rebuilt and old canonical IDs retain successor references. Realistic high-volume throughput is unmeasured.

## ADR 4 — DOI normalization

Implement a small syntax normalizer with a documented Crossref-style DOI grammar, URL/prefix removal, case folding and preservation of trailing punctuation. INSPIRE uses idutils; the broader identifier library is not required for the narrow DOI-only scope. This is a material departure from the PRD's suggested library-based normalization and is covered by explicit tests. It does not establish DOI existence or exhaustively cover historical identifier syntax. Invalid DOI raw values remain in snapshots.

## ADR 5 — Projection storage

Store canonical field values with version/path/policy in a JSON projection rather than a separate CanonicalFieldValue model. This makes the small fixed set of read fields inspectable together. Source records and membership history remain relational. No manual field correction UI is claimed. Printed and online dates retained in source snapshots are visible; the current projection chooses the source's dates object as a unit rather than merging all date alternatives.

## Extension decisions

| Extension | Decision | Concrete basis / dependency |
|---|---|---|
| Embeddings | Offline experiment, never association authority | Run on frozen grouped corpus; insufficient independently annotated hard negatives prevent integration into decision policy. See embedding-experiment.md. |
| OpenSearch | Deferred | PostgreSQL already provides DOI lookup and indexed trigram candidates. No measured retrieval/latency failure yet justifies a second projection. Requires an outbox, revision fencing and tested rebuild before integration; none are claimed. |
| React / TypeScript | Deferred | Dedicated Django comparison, provenance and withdrawal-preview pages cover the complete flow. No observed user study demonstrates a need for client-side state complexity. Revisit for bulk review or measured interaction problems. |
| Airflow | Deferred | Two bounded imports have no scheduled cross-workflow dependency graph. Durable database jobs suffice. Revisit when scheduling/backfills/dependencies exceed this importer. |
| MCP | Deferred | The versioned read API already exposes bounded evidence and provenance. No agent-client use case has been validated; a transport would require tool authorization, resource bounds and tests. |
| arXiv / edition relations | Deferred | Two providers are the PRD's initial acquisition boundary; explicit cross-edition relation editing needs its own model and reviewed cases. Preprints remain distinct in the current identity rules. |
| LLM / RAG | Not integrated | No independent labeled extraction/generation task or budget; probabilistic generated explanations would weaken deterministic evidence. |
| Public hosting / external review | Await explicit authorization / human participation | No publication, third-party messages, deployment or spending performed. |

These decisions do not make the complete PRD finished. Remaining target-volume load testing, independent annotation and observed user acceptance are recorded in status.md.
