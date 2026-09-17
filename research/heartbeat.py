"""A job lease refreshed independently of slow external operations."""

import logging
import threading
from contextlib import contextmanager

from django.db import close_old_connections, connection, connections, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


@transaction.atomic
def refresh(pk, run_id):
    from .models import Dossier

    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '1s'")
        cursor.execute("SET LOCAL statement_timeout = '2s'")
    return Dossier.objects.filter(pk=pk, run_id=run_id, status="running").update(
        updated_at=timezone.now()
    )


@contextmanager
def lease(dossier, interval=30):
    stop = threading.Event()

    def beat():
        try:
            while not stop.wait(interval):
                close_old_connections()
                try:
                    if not refresh(dossier.pk, dossier.run_id):
                        return
                except Exception:
                    logger.warning("Could not renew research job lease", exc_info=False)
        finally:
            connections.close_all()

    thread = threading.Thread(target=beat, daemon=True, name="research-heartbeat")
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=3)
