"""Durable, at-least-once imports with fenced leases and page checkpoints."""

import hashlib
import json
import uuid
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .connectors import PROVIDERS, ConnectorError, MetadataClient, snapshot
from .models import ImportFailure, ImportRun
from .services import ingest_record

LEASE_SECONDS = 120
FIXTURES = {"demo": "demo.json", "synthetic": "synthetic.json", "corpus": "corpus.json"}


class ImportConflict(ValueError):
    pass


class LeaseLost(RuntimeError):
    pass


class SimulatedCrash(RuntimeError):
    pass


def validate_profile(provider, profile):
    if provider not in PROVIDERS or not isinstance(profile, dict):
        raise ValueError("Choose crossref or openalex and a profile object.")
    if set(profile) - {"fixture", "page_size", "max_records", "query", "from_date", "until_date"}:
        raise ValueError("Unsupported profile parameter.")
    profile = dict(profile)
    if "fixture" in profile and profile["fixture"] not in FIXTURES:
        raise ValueError("Unknown fixture.")
    for key, default, maximum in [("page_size", 20, 100), ("max_records", 100, 1000)]:
        value = profile.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
            raise ValueError(f"{key} must be between 1 and {maximum}.")
        profile[key] = value
    if "query" in profile and (
        not isinstance(profile["query"], str) or len(profile["query"]) > 200
    ):
        raise ValueError("Query must be at most 200 characters.")
    for key in ("from_date", "until_date"):
        if profile.get(key):
            date.fromisoformat(profile[key])
    return profile


def create_import(provider, profile, idempotency_key=None):
    profile = validate_profile(provider, profile)
    digest = hashlib.sha256(json.dumps([provider, profile], sort_keys=True).encode()).hexdigest()
    if idempotency_key:
        if not isinstance(idempotency_key, str) or len(idempotency_key) > 128:
            raise ValueError("Invalid idempotency key.")
        run, created = ImportRun.objects.get_or_create(
            idempotency_key=idempotency_key,
            defaults={"provider": provider, "profile": profile, "request_hash": digest},
        )
        if not created and run.request_hash != digest:
            raise ImportConflict("Idempotency key was already used with different content.")
        return run
    return ImportRun.objects.create(provider=provider, profile=profile, request_hash=digest)


@transaction.atomic
def claim_run(run_id=None):
    now = timezone.now()
    query = ImportRun.objects.select_for_update(skip_locked=True).filter(
        Q(status="queued") | Q(status="running", lease_expires_at__lt=now)
    )
    query = query.filter(
        Q(cursor__not_before__isnull=True) | Q(cursor__not_before__lte=now.isoformat())
    )
    if run_id:
        query = query.filter(pk=run_id)
    run = query.order_by("created_at").first()
    if run:
        run.status, run.lease_owner = "running", str(uuid.uuid4())
        run.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        run.started_at = run.started_at or now
        run.save()
    return run


def _locked(run_id, owner):
    run = ImportRun.objects.select_for_update().get(pk=run_id)
    if (
        run.status != "running"
        or run.lease_owner != owner
        or not run.lease_expires_at
        or run.lease_expires_at <= timezone.now()
    ):
        raise LeaseLost("Import lease expired or was reclaimed.")
    return run


@transaction.atomic
def heartbeat(run_id, owner):
    run = _locked(run_id, owner)
    run.lease_expires_at = timezone.now() + timedelta(seconds=LEASE_SECONDS)
    run.save(update_fields=["lease_expires_at", "updated_at"])


def _fixture_page(run):
    path = Path(settings.BASE_DIR) / "data" / FIXTURES[run.profile["fixture"]]
    records = json.loads(path.read_text())
    records = [r for r in records if r.get("provider") == run.provider][
        : run.profile["max_records"]
    ]
    offset = run.cursor.get("offset", 0)
    items = records[offset : offset + run.profile["page_size"]]
    cursor = {"offset": offset + len(items)}
    return items, cursor, cursor["offset"] >= len(records)


def process_run(run_id=None, crash_after=None, client=None):
    run = claim_run(run_id)
    if run is None:
        return None
    owner, processed = run.lease_owner, 0
    client = client or MetadataClient(heartbeat=lambda: heartbeat(run.pk, owner))
    try:
        if not run.profile.get("fixture") and not settings.EXTERNAL_IMPORTS_ENABLED:
            raise ConnectorError(
                "external_disabled",
                "External acquisition is disabled; enable it explicitly for this worker.",
                False,
            )
        while True:
            heartbeat(run.pk, owner)
            run.refresh_from_db()
            if "page" in run.cursor:
                saved_page = run.cursor["page"]
                items, next_cursor, done = (
                    saved_page["items"],
                    saved_page["next_cursor"],
                    saved_page["done"],
                )
            else:
                items, next_cursor, done = (
                    _fixture_page(run)
                    if run.profile.get("fixture")
                    else client.page(run.provider, run.profile, run.cursor)
                )
                with transaction.atomic():
                    current = _locked(run.pk, owner)
                    current.cursor = {
                        **current.cursor,
                        "page": {"items": items, "next_cursor": next_cursor, "done": done},
                    }
                    current.save(update_fields=["cursor", "updated_at"])
            for index, item in enumerate(items):
                with transaction.atomic():
                    current = _locked(run.pk, owner)
                    pending = current.cursor.get("pending", {})
                    if str(index) in pending:
                        continue  # Persisted item outcome belongs to this not-yet-checkpointed page.
                    external_id = str(item.get("external_id") or "")
                    raw = item.get("raw")
                    try:
                        if not external_id or len(external_id) > 512:
                            raise ValueError("Missing or excessive source identifier.")
                        raw = snapshot(run.provider, raw)
                        _, status = ingest_record(run.provider, external_id, raw)
                    except (ValueError, TypeError, KeyError, AttributeError) as exc:
                        status = "rejected"
                        failure_raw = raw if isinstance(raw, dict) else {}
                        failure_id = (
                            external_id or f"item:{current.cursor.get('offset', 0) + index}"
                        )
                        if len(failure_id) > 512:
                            failure_raw = {
                                "record": failure_raw,
                                "invalid_external_id": external_id,
                            }
                            failure_id = (
                                "invalid-id:sha256:"
                                + hashlib.sha256(external_id.encode()).hexdigest()
                            )
                        ImportFailure.objects.update_or_create(
                            run=current,
                            external_id=failure_id,
                            defaults={
                                "raw": failure_raw,
                                "code": "invalid_record",
                                "message": str(exc)[:500],
                                "attempts": 1,
                                "retryable": False,
                                "resolved": False,
                            },
                        )
                    pending[str(index)] = status
                    current.cursor = {**current.cursor, "pending": pending}
                    current.lease_expires_at = timezone.now() + timedelta(seconds=LEASE_SECONDS)
                    current.save(update_fields=["cursor", "lease_expires_at", "updated_at"])
                processed += 1
                if crash_after and processed >= crash_after:
                    raise SimulatedCrash(
                        "Worker stopped after persistence and before page checkpoint; wait for lease expiry or use --expire-lease for the controlled demo."
                    )
            with transaction.atomic():
                current = _locked(run.pk, owner)
                counters = current.counters.copy()
                for status in current.cursor.get("pending", {}).values():
                    counters["read"] = counters.get("read", 0) + 1
                    counters[status] = counters.get(status, 0) + 1
                current.counters, current.cursor = counters, next_cursor
                if done:
                    current.status = (
                        "partially_failed"
                        if ImportFailure.objects.filter(run=current, resolved=False).exists()
                        else "succeeded"
                    )
                    current.finished_at, current.lease_owner, current.lease_expires_at = (
                        timezone.now(),
                        "",
                        None,
                    )
                current.save()
            if done:
                return current
    except SimulatedCrash:
        raise
    except LeaseLost:
        raise
    except (ConnectorError, OSError, json.JSONDecodeError) as exc:
        with transaction.atomic():
            current = _locked(run.pk, owner)
            ImportFailure.objects.create(
                run=current,
                external_id="",
                raw={},
                code=getattr(exc, "code", "fixture_error"),
                message=str(exc)[:500],
                attempts=1,
                retryable=getattr(exc, "retryable", False),
                resolved=False,
            )
            if getattr(exc, "retry_after", None):
                current.cursor = {
                    **current.cursor,
                    "not_before": (timezone.now() + timedelta(seconds=exc.retry_after)).isoformat(),
                }
            current.status, current.finished_at = "failed", timezone.now()
            current.lease_owner, current.lease_expires_at = "", None
            current.save()
        return current


@transaction.atomic
def retry_run(run_id):
    run = ImportRun.objects.select_for_update().get(pk=run_id)
    if run.status in ("queued", "running"):
        return run
    if run.status not in ("failed", "partially_failed"):
        raise ImportConflict("Only failed imports can be retried.")
    if run.cursor.get("not_before") and run.cursor["not_before"] > timezone.now().isoformat():
        raise ImportConflict("Provider Retry-After has not elapsed; retry later.")
    # Resume network failures at the checkpoint. Invalid record failures remain visible.
    ImportFailure.objects.filter(run=run, external_id="", resolved=False).update(resolved=True)
    run.status, run.finished_at, run.lease_owner, run.lease_expires_at = "queued", None, "", None
    run.save()
    return run
