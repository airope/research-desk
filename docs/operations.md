# Local operations

Use the same `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD` environment for every command. With Compose prefix commands by `docker compose exec web`; the worker service already polls. See README for installation.

## Import and inspect

`python manage.py demo` synchronously imports the committed demo snapshots and generates candidates. Repeating it preserves record/version counts and prior human decisions. `python manage.py import_records crossref --fixture demo --queue` queues work; its output includes the run UUID. `python manage.py worker --once` claims one eligible run. The persistent worker polls every two seconds.

The Imports screen and `/api/v1/imports/{uuid}` expose status, durable cursor, counters, lease expiration, failures and retry eligibility. Counters commit with the page checkpoint; pending item outcomes may already be durable before those counters advance. A failed page is resumed from the saved snapshot, so provider changes cannot shift partially processed items.

For real acquisition, external fetching is intentionally disabled unless explicitly set:

```sh
EXTERNAL_IMPORTS_ENABLED=1 python manage.py import_records crossref --query 'quantum optics' --max-records 100 --page-size 20
```

No URLs or credentials are accepted from visitors. Jobs cap records at 1000 and pages at 100. Provider clients use bounded attempts/timeouts and serial request pacing. A long Retry-After becomes a persisted earliest retry time; don't repeatedly retry before it. 401/403 stops acquisition. Invalid bibliographic items retain terminal failures while valid siblings continue. Retryable network failures resume at the checkpoint; invalid items require a corrected new source snapshot/import, not silent mutation of audit data.

## Controlled interruption and recovery

Queue an offline run and copy its UUID:

```sh
python manage.py import_records crossref --fixture demo --queue
python manage.py worker --once --run-id UUID --crash-after 2 --expire-lease --hard-crash
python manage.py worker --once --run-id UUID
```

The fault hook exits with code 137 after committing item outcomes and before page acknowledgement. `--expire-lease` is a controlled-demo convenience that avoids waiting 120 seconds; ordinary process death relies on natural lease expiry. Run the fault demonstration with no competing worker if you need that exact run to be claimed. Replaying the completed fixture creates no duplicate versions. Never use fault-injection flags for operational imports.

If a real worker disappears, inspect the lease and restart the worker. `select_for_update(skip_locked=True)` prevents duplicate claims, a new owner token fences stale workers, and lease renewal protects active work. No direct database repair is necessary. Server or database failures require restoring service before the lease can be reclaimed. The worker is supervised by your local process/container runner, not by an embedded generic scheduler.

## Health and diagnosis

- `/health/live`: process alive.
- `/health/ready`: PostgreSQL reachable; 503 when it is unavailable.
- HTTP response `X-Request-ID` correlates structured request status logs. Import run IDs and failure codes are available in worker output and API.
- `python manage.py check` and `python manage.py makemigrations --check --dry-run` validate configuration/schema drift.
- The catalogue is a PostgreSQL projection; no OpenSearch index is currently integrated.

## Backup and restore

Use PostgreSQL 17 client tools. Backups contain local users, sessions and decisions; keep them out of the repository.

```sh
pg_dump --format=custom --file=/safe/local/path/srr.dump srr
createdb srr_restore_check
pg_restore --exit-on-error --no-owner --dbname=srr_restore_check /safe/local/path/srr.dump
PGDATABASE=srr_restore_check python manage.py check
PGDATABASE=srr_restore_check python manage.py shell -c 'from records.models import SourceRecord,ReviewDecision; print(SourceRecord.objects.count(),ReviewDecision.objects.count())'
```

Use a new restore database, never overwrite an existing catalogue as an unannounced reset. Compare record/version/decision counts and actual projections before selecting a restored database for use. A native dump/restore round trip was exercised during validation; see validation.md. No destructive reset command is supplied.

## Isolated validation runtime used on this host

Docker was absent. PostgreSQL 17.11 from the official Postgres.app distribution was extracted to `/tmp/srr-postgres-runtime`, bound to 127.0.0.1:55432, with dedicated data and log directories. The cluster uses local trust for the isolated demonstration and must never be publicly exposed. Native Python 3.12.14 supplied by Codex was used because the Homebrew Python3.14 installation failed interpreter inspection. These are environment facts, not portable installation prerequisites.
