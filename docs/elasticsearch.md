# Elasticsearch passage retrieval

Elasticsearch is an optional real search backend for Research desk. INSPIRE still supplies bibliographic records. PostgreSQL remains the source of truth for dossiers and evidence; Elasticsearch is a rebuildable passage index.

## What is implemented

- Official Elasticsearch Python 8.19 client; Elasticsearch 8.19.21 runtime pinned for reproducible local setup.
- `research-passages-v1`: strict mapping, English text analyzer, default BM25 scoring, keyword scope/corpus/paper IDs and physical page numbers.
- Worker-side bulk indexing with stable per-source IDs; unchanged sources skip bulk writes. Page retrieval performs only a completeness check and one multi-search request.
- A source-content digest excludes outdated chunks. Every query filters by owner/dossier scope, current source revision, selected paper and PDF page. Returned IDs are resolved against current application-owned text; stale or foreign hits are rejected.
- Follow-up questions drive ranking directly; broad original context is still supplied to the model but no longer dilutes the retrieval query. The exact search query is retained with report provenance.
- Top five PDF chunks per paper, within 4,000 characters per paper/80,000 total, with separate abstract context. BM25 is lexical search, not semantic/vector retrieval.
- Find passages tab allows direct text search without a model request. Generated reports retain the exact model passages, engine, scores and fallback warning.
- Timeouts, failed shards and foreign hits produce an explicit unavailable result; no local-keyword ranking silently replaces Elasticsearch. Indexing failures stop publication and retain saved sources. Scientific confidence is never inferred from search scores.

## Configuration

```sh
RESEARCH_SEARCH_BACKEND=elasticsearch
RESEARCH_ELASTICSEARCH_URL=http://127.0.0.1:9200
RESEARCH_ELASTICSEARCH_API_KEY=<an index-scoped API key>
# For a TLS endpoint, optionally supply its CA bundle:
RESEARCH_ELASTICSEARCH_CA_CERTS=/path/to/ca.crt
```

Set the same configuration on the Django web process and `research_worker`. Keep credentials out of Git, browser pages and model prompts. TLS verification is enabled; use HTTPS for any non-loopback deployment.

Optional Compose service:

```sh
RESEARCH_ELASTIC_PASSWORD='<your-local-password>' docker compose -f compose.yaml -f compose.search.yaml --profile search up -d elasticsearch
```

The optional service is loopback-bound and authenticated. Create a server-side API key for `research-passages-v1` with only `create_index`, `read`, `write` and `maintenance` index privileges using an authorized administrator. No cluster privileges are needed by the application. The worker creates its index on source publication; retrieval never creates it. Native macOS archives also work; consult the official archive instructions.

## Validation and current host state

Unit/integration tests use deterministic Elasticsearch doubles to cover request filters, deterministic IDs, stale corpus isolation, incomplete results, bulk failure handling, ranking order, text budgets, owner-scoped routes and visible source highlighting. They do not establish real-cluster correctness or retrieval quality.

On 2026-09-17 the official macOS arm64 8.19.21 archive was downloaded, SHA-512 verified and an authenticated loopback node started in `/tmp/research-elasticsearch-runtime`. With the user's explicit approval, local disk thresholds were set to2GB/1GB/512MB and an application key restricted to `research-passages-v1` was created. The credential stays in a mode0600 file outside the repository; it is loaded into web/worker process environments.

Historical measurements before the audit corrections: real-cluster indexing/search succeeded:167 passages; repeated indexing kept167 documents. The query `latency throughput FPGA resources` returned11 budgeted PDF passages, led by FPGA pages20 and17. Full application retrieval (bulk indexing, refresh and six searches) took1.212s then0.996s on this dossier; these are individual observations, not a load benchmark. Browser verification displayed Elasticsearch/BM25 and the page20 performance table. The web and research worker now use Elasticsearch. A live model report completed with `elasticsearch-bm25` provenance and exact passages retained. The focused long-form query still missed the numerical FPGA table chunk, although the shorter manual query found it; this remains a retrieval-quality limitation, not a claim of measured improvement. Earlier reports keep their original retrieval provenance. Authentication checks confirmed anonymous requests are rejected, an unrelated scope returns zero hits and the application key cannot read cluster health.

Native restart, while the `/tmp` runtime remains available:

```sh
ES_JAVA_OPTS='-Xms512m -Xmx512m' /tmp/research-elasticsearch-runtime/elasticsearch-8.19.21/bin/elasticsearch
```

For the application terminals, set the variables above, including the approved key stored privately in `/tmp/research-elasticsearch-runtime/api-key`, then run Django and `research_worker` as described in the research guide. Do not paste the key into a report, source file or shared terminal output. The disk settings apply only to this isolated local node.

## Limits and next measurements

Indexing now occurs in the research worker. Obsolete source revisions are purged after successful indexing, and deletion hooks remove dossier scopes. Run `python manage.py reindex_research` to rebuild existing dossiers and `python manage.py reindex_research --purge-orphans` to retry deletion cleanup after an outage. Consult [deployment](deployment.md) for separate read/write credentials. Load tests are still required before a shared deployment. Scope filters are enforced by trusted application code; a shared index is not a replacement for Elasticsearch document-level security against direct cluster users. BM25 statistics are shared across the index, although returned content is scope-filtered.

Measure BM25 against the existing lexical baseline on independently annotated questions using the protocol in `research-evaluation.md`. No quality gain or latency improvement has yet been measured. This code targets Elasticsearch; OpenSearch compatibility is not claimed.

## Primary references

- [Official Python client](https://www.elastic.co/docs/reference/elasticsearch/clients/python/getting-started)
- [Elasticsearch 8.19 archive installation](https://www.elastic.co/guide/en/elasticsearch/reference/8.19/targz.html)
- [Docker installation](https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-with-docker)

## Audit hardening validation

The current implementation was checked against the real local cluster for stable IDs, subset retrieval without writes, obsolete revision cleanup and scope isolation. Browser search now issues `_count` and `_msearch` only. See [audit corrections](audit-corrections-2026-09-17.md) for validation and remaining deployment limits.
