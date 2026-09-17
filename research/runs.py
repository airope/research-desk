"""Measured local operations; no inferred token usage or monetary estimates."""

import time

from django.db import transaction
from django.utils import timezone

from .models import ResearchRun


def timed(run_id, label, call, *args, **kwargs):
    start = time.monotonic()
    success = False
    try:
        result = call(*args, **kwargs)
        success = not (
            isinstance(result, dict) and result.get("status") in {"failed", "unavailable"}
        )
        return result
    finally:
        with transaction.atomic():
            run = ResearchRun.objects.select_for_update().filter(pk=run_id).first()
            if run:
                run.metrics.append(
                    {
                        "operation": label,
                        "seconds": round(time.monotonic() - start, 2),
                        "success": success,
                    }
                )
                run.save(update_fields=["metrics"])


def finish(run_id, status, error=""):
    ResearchRun.objects.filter(pk=run_id).update(
        status=status, error=error[:500], finished_at=timezone.now()
    )
