from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections

from records.models import ReviewDecision, SourceRecord
from records.services import DomainError, decide, ingest_record
from tests.test_domain import pair, record


@pytest.mark.django_db(transaction=True)
def test_two_curators_cannot_overwrite_each_other():
    value = pair(record("a"), record("b"))
    barrier = Barrier(2)

    def run(actor):
        close_old_connections()
        barrier.wait()
        try:
            result = decide(value.pk, "accept", actor, "", value.revision, actor)
            return str(result.pk)
        except DomainError as exc:
            return exc.code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ["alice", "bob"]))
    assert results.count("stale_revision") == 1
    assert ReviewDecision.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_import_deduplicates_source_and_version():
    barrier = Barrier(2)

    def run(_):
        close_old_connections()
        barrier.wait()
        try:
            return ingest_record("crossref", "one", {"title": ["Concurrent"]})[1]
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert sorted(results) == ["created", "unchanged"]
    assert SourceRecord.objects.get().versions.count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_transitive_accept_reject_cannot_create_contradictory_group():
    a, b, c = record("a"), record("b"), record("c")
    ab, bc, ac = pair(a, b), pair(b, c), pair(a, c)
    decide(ab.pk, "accept", "first", "", ab.revision, "first")
    bc.refresh_from_db()
    ac.refresh_from_db()
    barrier = Barrier(2)

    def run(spec):
        candidate, action = spec
        close_old_connections()
        barrier.wait()
        try:
            decide(candidate.pk, action, action, "Reviewed", candidate.revision, action)
            return "ok"
        except DomainError as exc:
            return exc.code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, [(bc, "accept"), (ac, "reject")]))
    assert results.count("ok") == 1
    assert set(results) & {"stale_revision", "group_rejection"}
