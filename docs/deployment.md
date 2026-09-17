# Running and deployment

The source release supports **trusted local use only**. The production profile below is a configuration contract for a possible future deployment, not authorization to expose this release. External hosting remains blocked until the target environment passes an independent security review and the acceptance checks below. See [security policy](../SECURITY.md).

## Local demonstration with Docker Compose

`compose.yaml` deliberately provides a loopback development configuration with demonstration credentials. Do not publish its ports on the Internet or expose it through a public tunnel.

```sh
cp .env.example .env
docker compose up --build -d
docker compose exec web python manage.py createsuperuser
```

The `init` service applies migrations before `web`, `worker` (legacy reconciliation) and `research_worker` (INSPIRE research) start. Check `docker compose logs research_worker` to confirm queue processing. Manual INSPIRE search works without AI. Configure API providers through `.env`; see [LLM providers](llm-providers.md). The image does not include the Codex CLI or receive a personal account. API adapters support the production profile with injected keys; that does not establish hosting readiness.

Personal Codex is **experimental and disabled by default**. The adapter is restricted to a local workstation with the official CLI and explicit `RESEARCH_CODEX_ENABLED=1`, the configured local account and development settings. Production refuses this mode. Do not mount personal credentials into a shared server. Effective CLI tool/configuration isolation is not independently certified: a temporary working directory and read-only flags do not by themselves prevent private-file reads. Keep this mode disabled pending isolated validation with harmless canaries and a synthetic environment; do not use real user credentials or private files to test its isolation.

PostgreSQL persists in `pgdata`; `docker compose down -v` destroys that volume. Before an update, back up with `pg_dump` and test restoration into a separate database. A Docker volume is not a backup.

## Optional Elasticsearch

1. Set a unique `RESEARCH_ELASTIC_PASSWORD` in `.env`, then start the engine:

   ```sh
   docker compose -f compose.yaml -f compose.search.yaml --profile search up -d elasticsearch
   ```

2. Create a least-privilege API key. This command prompts for the administrator password rather than placing it in shell history. Its response contains a secret: keep it only in private configuration, never in logs or shared output. Recommended local permissions: `chmod 600 .env`.

   ```sh
   curl --user elastic -H 'Content-Type: application/json' \
     http://127.0.0.1:9200/_security/api_key -d '{"name":"research-local","role_descriptors":{"research":{"cluster":[],"indices":[{"names":["research-passages-v1"],"privileges":["create_index","read","write","maintenance"]}]}}}'
   ```

3. Copy the `encoded` field into `RESEARCH_ELASTICSEARCH_API_KEY`, set `RESEARCH_SEARCH_BACKEND=elasticsearch` and retain `RESEARCH_ELASTICSEARCH_URL=http://elasticsearch:9200` for containers. The administrator password is not passed to the application. A separate query key may be injected as `RESEARCH_ELASTICSEARCH_READ_API_KEY`, with only `read` privilege on `research-passages-v1`. Without it, the demo reuses the main key. Any future shared deployment must separate process secrets: a write key for the worker, a read key for the web process. Local Compose deliberately shares the same variables.

   ```sh
   docker compose -f compose.yaml -f compose.search.yaml --profile search up --build -d
   ```

The healthcheck verifies that the authenticated engine responds. Check `docker compose -f compose.yaml -f compose.search.yaml --profile search ps` before the first search. For native Python on the workstation, use `http://127.0.0.1:9200` instead of the Docker service name.

## Variables and secrets

Django loads the project's `.env` without replacing process variables. Compose uses `.env` to interpolate only variables explicitly included in `compose.yaml`. For a native launch, edit the private local `.env` or inject variables through the process manager. `.env*` files are excluded from Git and the Docker build context except for the secret-free example. A future hosted environment must inject secrets through its secret manager; never copy `.env` into an image.

## Production profile

The profile explicitly requires:

- `APP_ENV=production` (or `DEBUG=0`, which also enables the safeguards);
- `DEBUG=0` or omitted;
- a unique, random `SECRET_KEY` of at least 50 characters;
- a nonempty `PGPASSWORD` different from the demonstration password;
- explicit `ALLOWED_HOSTS` without `*`, plus the actual PostgreSQL settings.

Startup rejects invalid configuration and personal Codex activation. Secure cookies, HTTPS redirection and HSTS are enabled. Set `TRUST_HTTPS_PROXY=1` only behind a controlled proxy that strips incoming `X-Forwarded-Proto` headers and sets its own value. The application server must not be directly accessible. Set `CSRF_TRUSTED_ORIGINS` when needed; do not add arbitrary origins. HSTS subdomains and preload remain opt-in after DNS/TLS review. The only deliberately silenced deployment warnings are W005 and W021: those commitments apply across the domain and cannot be imposed without reviewing its subdomains. HSTS itself remains mandatory in production; all other warnings remain active.

The image starts Gunicorn and collects static files during its build. Local Compose overrides that command with `runserver`; it is not a production manifest. A future host must supply TLS, static-file serving, supervision for both workers, backups and tested restoration, logging, resource limits and authenticated Elasticsearch on a private network (TLS outside the local workstation). Validate injected settings with:

```sh
python manage.py check --deploy --fail-level WARNING
```

CI configuration checks this profile and configuration files. Those checks do not prove proxy behavior, backup recovery or load capacity, and the existence of a CI definition is not evidence of a successful run. Acceptance remains specific to the deployed environment.

## Mandatory ingress limits before any external hosting

The CSV form's **2 MiB file limit is post-ingestion validation**, not a hard transport-body or temporary-disk cap. Django may parse multipart data and spool uploaded files to disk before rejecting the form. `DATA_UPLOAD_MAX_MEMORY_SIZE`, authentication, CSRF and per-user quotas do not establish a total upload bound.

Before any exposure to untrusted clients, the operator must configure and test all of the following:

- A front-proxy total request-body limit, with a deliberately bounded allowance for multipart overhead, enforced before forwarding oversized uploads. Bound aggregate multipart bodies, not just one file; prevent direct application-server access.
- Header/body request timeouts and slow-upload protection at ingress, plus appropriate upstream timeouts.
- Temporary-disk quotas and resource limits for both proxy buffering and application upload spooling. Review any early upload-handler limits as defense in depth, not a substitute for ingress enforcement.
- Isolated tests showing oversized requests are rejected without excessive temporary writes. Include unauthenticated requests, missing-CSRF requests, multiple-file multipart bodies, slow uploads and attempts to bypass the proxy. Measure disk behavior, not only the final HTTP status.

No such hosting acceptance is implied by this documentation. Keep the source release on a trusted local workstation until these controls and the wider deployment review have passed.

## PDF isolation and workers

The image includes Bubblewrap. The Linux host must allow it to operate with compatible user namespaces and runtime policy. Do not enable privileged-container mode to bypass a failure: review and adapt the policy or use an isolated parsing service. If the sandbox cannot start, PDF extraction fails in a controlled way; metadata remains usable. Test a real public PDF after installation: the presence of the binary alone does not prove execution. On macOS, parsing uses `sandbox-exec`.

`RESEARCH_PDF_ALLOW_UNSANDBOXED_LOCAL=1` is an explicit development-only fallback when the isolation tool is missing; do not enable it for untrusted PDFs. The production profile rejects this fallback. Workers on one host share an arXiv rate-limit lock in `/tmp`; multiple research containers must share a writable local volume and point `RESEARCH_ARXIV_STATE` to the same file. This file lock does not coordinate multiple hosts; that requires a distributed rate limiter.

## Migrating existing source text

After `migrate`, newly saved dossiers store abstracts and PDF pages in `SourceSnapshot`, once per content value per dossier. Reports and history retain immutable references; normal `dossier.papers`, `report_papers` and `versions` access resolves them on demand. To compact dossiers created before this storage format:

```sh
python manage.py compact_research_sources
```

The command is idempotent, locks each dossier and verifies content equality after reloading before committing its transaction. `--dossier UUID` limits the scope. Back up PostgreSQL before any migration. Snapshots live in the same database and cascade-delete with their dossier. Historical snapshots still referenced by a report are retained to avoid invalidating old citations.

To remove abandoned revisions, use `compact_research_sources --prune-unreferenced --offline` **only after stopping the web process and research workers**. A row lock does not protect readers that have already loaded references into memory. `--offline` confirms that shutdown; the command refuses pruning without confirmation and does not detect remote processes itself. Compaction without pruning can remain online. Under the same lock, the command compares source, report and all retained-version references, then removes only orphaned snapshots for that dossier.

For developers: use `Dossier.save()` to change the three source fields. `QuerySet.update()` and `bulk_create()` bypass normalization; `values()` intentionally returns raw references without loading texts. SQL updates limited to statuses and events remain appropriate. Do not modify existing `SourceSnapshot` rows: a correction creates new content and a new hash.

## Elasticsearch CI contract

The CI definition starts a disposable Elasticsearch 8.19.21 with a 512 MB heap, without personal credentials or LLM calls. Authentication is disabled **only for this runner test service**; deployment files retain an authenticated engine. The opt-in `tests/test_research_elasticsearch_integration.py` test uses a UUID index name prefixed with `test-research-`, removed in a `finally` block. It checks real bulk/msearch operations, stable IDs, reading a selection without writes and dossier-scoped cleanup. It is skipped outside CI unless `RESEARCH_TEST_ELASTICSEARCH_URL` is set. For an authenticated test engine, inject `RESEARCH_TEST_ELASTICSEARCH_API_KEY`, restricted to `test-research-*` with the necessary test privileges (`manage`, `read`, `write`). Never point this test at a production engine. A configured service or test is not proof that the current revision has passed CI; verify the actual run separately.

Network deadlines cover response headers and bodies (INSPIRE 30 s, PDFs 60 s). DNS resolution still depends on the system resolver; the application does not guarantee real-time interruption of a blocked resolver. An explicit host validation is available through `RUN_PDF_SANDBOX_TEST=1` in the PDF tests. Revalidate the actual sandbox on the target host; do not infer it from an earlier workstation run.

## Consumption limits and maintenance

Counters are shared through PostgreSQL: logins by IP/account, writes and searches by user, dossier creation, daily jobs and active queue limits. `LOGIN_ATTEMPTS_PER_WINDOW`, `USER_WRITES_PER_MINUTE`, `USER_SEARCHES_PER_MINUTE`, `RESEARCH_DAILY_DOSSIERS`, `RESEARCH_DAILY_JOBS`, `RESEARCH_MAX_ACTIVE_PER_USER` and `RESEARCH_MAX_ACTIVE_GLOBAL` must be positive integers. Reaching a limit returns 429 with Retry-After; cancelling work remains possible. These are work limits, not monetary or token spending caps. The middleware does not trust X-Forwarded-For: behind a proxy, configure client addresses in the trusted server layer or add separate login protection. Run `python manage.py cleanup_research_limits` daily.

PDF/INSPIRE deadlines include headers and bodies on a new connection; DNS remains dependent on the system resolver. The job heartbeat uses short SQL timeouts; processing locks must not block it indefinitely.

Run `python manage.py reindex_research --purge-orphans` with the write account to catch up on deletions after an engine outage or when the web process uses only a read key. Web searches never reindex.

## Data retention and operator access

CSV imports preserve unknown columns in the original row and retain the uploaded filename. Remove unneeded columns and identifying filenames **before uploading**; selecting displayed bibliographic fields is not a data-minimization or erasure mechanism.

Operators can access the database, source snapshots and report history, Elasticsearch passages, logs, exports and backups. Establish retention and deletion procedures for every store, including old backups and provider-side copies, and use host/disk and backup encryption where appropriate. Dossier deletion and source compaction do not prove that all copies have disappeared; reconcile orphaned search entries and verify restoration does not silently reintroduce deleted data. The application does not provide comprehensive retention/compliance automation. See [privacy and network behavior](privacy-and-network.md).
