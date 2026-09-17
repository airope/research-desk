# Engineering evidence


| Engineering area | Inspectable project evidence | Limit |
|---|---|---|
| Python/Django, APIs, relational data | Django services, PostgreSQL constraints/transactions, source snapshots, REST schema and owner-scoped dossiers | Does not demonstrate years of production ownership |
| Data workflows | Durable queue, retries requested by user, cancellation fences, heartbeat, bounded acquisition and provenance | No operating SLA or measured large-scale workload |
| Scientific information | INSPIRE API search, scientific metadata, citations, source passages, preserved report versions | No independent domain-expert validation |
| LLM integration and RAG | Search planning, evidence retrieval, structured synthesis and bounded investigation; explicit multi-provider adapters | Adapter contracts tested; not every paid model exercised live, no independent scientific-quality benchmark |
| Elasticsearch retrieval | Real BM25 passage index, mappings, bulk publication, read-only retrieval and lifecycle cleanup | OpenSearch compatibility not claimed; retrieval is lexical, not semantic |
| Quality and security | PostgreSQL concurrency tests, provider failure contracts, OS-isolated PDF parser, quotas and CI configuration | CI configuration is not evidence of a GitHub run; Docker/Linux runtime still needs target-host validation |
| Architecture | Provider boundary, commands outside HTTP views, immutable source storage, documented operational tradeoffs | No external team adoption or operational history |
| Other optional technologies | Embeddings experiment separately documented | React/TypeScript, Airflow and MCP are not implemented in this application; no credit claimed for merely listing them |

The most useful demonstration is a scientific question → explicit search plan → selected articles → cited report → source verification, followed by a code walkthrough of a failed provider call, cancellation and index reconstruction. Tests and limitations should be easy to reproduce. More provider names are not a substitute for evidence quality or a maintainable user workflow.
