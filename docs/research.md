# Research and component selection

Primary sources checked 2026-09-17. This project is independent and is not commissioned by CERN.

- [INSPIRE](https://github.com/inspirehep/inspirehep) and its [literature record implementation](https://github.com/inspirehep/inspirehep/blob/master/backend/inspirehep/records/api/literature.py) already handle scientific metadata, identifier normalization, enrichment and merging. Reviewed as an architectural reference; no code copied. This project emphasizes reversible human decisions and version-level provenance.
- [Findpapers](https://github.com/jonatasgrosman/findpapers) offers multi-source search, enrichment and duplicate merging. Documentation examined, algorithm not audited. Its search scope is broader; source-preserving reconciliation is our specific domain responsibility.
- [Django 5.2 compatibility](https://docs.djangoproject.com/en/5.2/faq/install/), [PostgreSQL requirements](https://docs.djangoproject.com/en/5.2/ref/databases/): LTS Django with Python 3.12; PostgreSQL >=14 and psycopg >=3.1.8. Exact resolved Python packages are in uv.lock. Local validation targets PostgreSQL 17.11.
- [Django PostgreSQL search](https://docs.djangoproject.com/en/5.2/ref/contrib/postgres/search/): indexed trigram candidates avoid materializing a global quadratic pair matrix. Exact DOI matches remain a separate union.
- [Django row locking](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update): locking is transaction-scoped and must be tested with actual independent transactions, not inferred from SQLite tests.
- [Crossref access](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/): public API without key; observe current rate/concurrency headers, bounded serial collection and Retry-After. Contact email is operator configuration, never copied from application documents.
- [Crossref reuse](https://www.crossref.org/documentation/retrieve-metadata/rest-api/): bibliographic metadata is generally reusable; abstracts may be copyrighted and are omitted from distributed snapshots.
- [OpenAlex authentication](https://help.openalex.org/api/authentication/) and [costs](https://help.openalex.org/access/example-costs/): anonymous $0.10/day budget; singleton requests free; free account $1/day. No paid key or paid requests configured. Current list page size max100.
- [OpenAlex data](https://help.openalex.org/data/how-its-built/): CC0 metadata and upstream Crossref dependency. Two provider records are not independent evidence of bibliographic correctness.

Reused components: Django ORM/auth/forms/templates, DRF schema/serialization, httpx HTTP transport, RapidFuzz lexical comparison, psycopg PostgreSQL driver, pytest and Ruff. Custom code is limited to publication identity rules, audit/withdrawal graph semantics, provenance projection, bounded provider adapters and benchmark protocol. No generic workflow scheduler or homemade authentication.
