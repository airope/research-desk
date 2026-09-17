"""Database-backed admission limits, shared by all application processes."""

import hashlib
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone


@dataclass
class LimitExceeded(Exception):
    message: str
    retry_after: int = 60

    def __str__(self):
        return self.message


def configured(name, default):
    return int(getattr(settings, name, default))


@transaction.atomic
def consume(scope, identity, limit, seconds):
    from .models import UsageBucket

    key = hashlib.sha256(f"{scope}:{identity}".encode()).hexdigest()
    now = timezone.now()
    bucket, _ = UsageBucket.objects.select_for_update().get_or_create(
        key=key, defaults={"started_at": now}
    )
    if now >= bucket.started_at + timedelta(seconds=seconds):
        bucket.started_at, bucket.count = now, 0
    if bucket.count >= limit:
        remaining = max(
            1, int((bucket.started_at + timedelta(seconds=seconds) - now).total_seconds())
        )
        raise LimitExceeded("Too many requests. Please try again later.", remaining)
    bucket.count += 1
    bucket.save(update_fields=["started_at", "count"])


def admit_job(owner_id):
    """Call inside the same transaction as enqueueing; no network I/O under this lock."""
    from .models import Dossier

    if not connection.in_atomic_block:
        raise RuntimeError("Job admission requires a transaction")
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [873216492])
    active = Dossier.objects.filter(status__in=["queued", "running"])
    if active.filter(owner_id=owner_id).count() >= configured("RESEARCH_MAX_ACTIVE_PER_USER", 2):
        raise LimitExceeded("You already have active research jobs. Wait or stop one first.")
    if active.count() >= configured("RESEARCH_MAX_ACTIVE_GLOBAL", 50):
        raise LimitExceeded("The research queue is full. Please try again later.")
    consume("jobs-daily", owner_id, configured("RESEARCH_DAILY_JOBS", 30), 86400)
