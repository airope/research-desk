# Current user-facing milestone

Research desk is now the primary interface. See [Research MVP](research-mvp.md) for actual capabilities and explicit limitations. It uses live INSPIRE abstracts, bounded arXiv/INSPIRE PDF extraction, page-linked citations, focused follow-ups and report history, powered by the official local Codex CLI with the workstation owner's ChatGPT login. Research-generation quality has not been benchmarked; quote presence validation is not entailment validation.

The previous catalogue milestones below remain available independently.

# Delivered, experimental and remaining

As of 2026-09-17. This is a working local implementation, not a declaration that every PRD target has been met.

| Capability | State | Evidence / remaining limit |
|---|---|---|
| Source ingestion and history | Delivered and tested | Real Crossref/OpenAlex snapshots; repeated imports idempotent; immutable source version triggers. |
| Durable processing | Delivered and tested | Expiring fenced leases, frozen pages, terminal failures and Retry-After deadlines; actual worker exit137 recovery regression. |
| Explainable candidates | Delivered and tested | PostgreSQL trigram K+exact DOI union, deterministic ties, versioned evidence and missing/conflicting signals. |
| Human accept/reject/defer/withdraw | Delivered and tested | Revision/idempotency guards, transitive rejection constraints, dependent-link preview and component splits. |
| Catalogue/provenance/API | Delivered and browser-tested | Source/version/path/policy per chosen field, old IDs with successors, paginated API and generated OpenAPI. |
| Offline demonstration | Delivered | 100 real provider snapshots, synthetic fixture and no provider key required after installation. |
| Functional corpus | Acquired and imported | 1,000 real provider notices, 500/provider; one journal/year and DOI-selection bias. |
| Benchmark | Delivered, exploratory | 200 labeled pairs:150 synthetic and50 DOI weak labels; group-disjoint partitions; no expert/manually verified real labels. |
| Embeddings | Executed experiment only | Frozen MiniLM ONNX, checksums and offline rerun; no observed candidate gain; not used by app. |
| Automatic association | Deliberately disabled | Independent annotations insufficient to justify precision target. |
| PostgreSQL backup/restore | Exercised | Dump restored into separate DB with preserved source/version/decision counts. |
| Docker Compose and CI | Configured, not executed here | Docker unavailable and no remote publication authorized; native startup/tests actually ran. |
| 10,000-notice HTTP p95 target | Not established | Smaller in-process workload reported separately; not equivalent to target load. |
| Observed independent usability test | Not performed | Developer browser walkthrough completed; independent participant still needed. |
| Catalogue field correction | Delivered for private user catalogues | Title, DOI, year and journal with reasons and immutable audit; public reference graph keeps source-priority projection. |
| Cancellation UI, scheduled pipelines | Not implemented | Worker interruption/recovery delivered; explicit user cancellation and orchestration require further behavior design. |
| OpenSearch / React / Airflow / MCP | Deferred with concrete conditions | See decisions.md; these technologies are not claimed as demonstrated. |
| External review, hosted demo, PR | Not performed | Requires human participation or explicit publication authorization. |

## User-workflow milestone

Delivered: private per-user catalogues, bounded CSV import with persistent preview/errors, simulated baseline/incoming cases, live guided INSPIRE search and frozen selection, scoped duplicate/conflict review, add/merge/exclude/defer/reset, changes-only field corrections, CSV result and audit downloads with explicit unresolved policy. No private rows are inserted into the public reference graph. Limits: 500 baseline rows, 100 incoming hits/search, 1,000 entries/catalogue. Changed previously imported provider IDs are reported and retained unchanged, not silently refreshed.

Still outside this milestone: CDS/internal database connectors, BibTeX/RIS exports, author identity autocomplete, pagination beyond the explicit INSPIRE selection cap, scheduled synchronization, writeback to institutional systems and validated multi-version work identity. The first delivery completes the CSV→INSPIRE→review→CSV path; it does not complete every original PRD or subsequent extension.

## Next substantive milestone

Independently annotate real hard negatives and no-DOI positives, freezing publication-family splits before tuning. The current weak labels cannot validate an automatic identity policy or representative embedding performance. Then measure end-to-end HTTP load at the PRD volume and run a five-case independent curator walkthrough. These are explicit remaining acceptance criteria, not silently removed requirements.

Before Internet deployment: replace demonstration secrets, configure HTTPS/cookies and static serving, add login abuse protection and appropriate distributed limits, disable writes/acquisition for public users, and execute the container/CI path in a clean host. No public deployment has been attempted.
