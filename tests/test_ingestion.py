from datetime import timedelta

import pytest
from django.utils import timezone

from records.connectors import ConnectorError
from records.ingestion import (
    ImportConflict,
    LeaseLost,
    SimulatedCrash,
    claim_run,
    create_import,
    heartbeat,
    process_run,
    retry_run,
)
from records.models import ImportFailure, ImportRun, SourceRecord, SourceRecordVersion

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def enable_mock_acquisition(settings):
    settings.EXTERNAL_IMPORTS_ENABLED = True


class Pages:
    def __init__(self, bad=False, failure=False):
        self.bad, self.failure = bad, failure

    def page(self, provider, profile, cursor):
        if self.failure:
            raise ConnectorError("transport", "Test connection failure")
        return (
            [
                {
                    "external_id": str(i),
                    "raw": {
                        "DOI": f"10.1000/{i}",
                        "title": {"bad": True} if self.bad and i == 1 else [f"Example {i}"],
                    },
                }
                for i in range(3)
            ],
            {"offset": 3},
            True,
        )


def test_import_reimport_idempotent():
    for _ in range(2):
        run = process_run(create_import("crossref", {}).pk, client=Pages())
    assert run.status == "succeeded"
    assert run.counters == {"read": 3, "unchanged": 3}
    assert SourceRecord.objects.count() == SourceRecordVersion.objects.count() == 3


def test_crash_after_persistence_resumes_checkpoint_without_duplicate():
    run = create_import("crossref", {})
    with pytest.raises(SimulatedCrash):
        process_run(run.pk, client=Pages(), crash_after=2)
    run.refresh_from_db()
    assert run.status == "running" and run.cursor.get("offset", 0) == 0
    assert SourceRecord.objects.count() == 2
    ImportRun.objects.filter(pk=run.pk).update(
        lease_expires_at=timezone.now() - timedelta(seconds=1)
    )
    done = process_run(run.pk, client=Pages())
    assert done.counters == {"read": 3, "created": 3}
    assert done.cursor == {"offset": 3}
    assert SourceRecord.objects.count() == SourceRecordVersion.objects.count() == 3


def test_invalid_item_visible_and_others_continue():
    done = process_run(create_import("crossref", {}).pk, client=Pages(bad=True))
    assert done.status == "partially_failed"
    assert done.counters == {"read": 3, "created": 2, "rejected": 1}
    assert ImportFailure.objects.get(run=done).code == "invalid_record"


def test_lease_fencing_and_claim_exclusivity():
    queued = create_import("crossref", {})
    first = claim_run(queued.pk)
    assert claim_run(queued.pk) is None
    ImportRun.objects.filter(pk=queued.pk).update(
        lease_expires_at=timezone.now() - timedelta(seconds=1)
    )
    second = claim_run(queued.pk)
    assert first.lease_owner != second.lease_owner
    with pytest.raises(LeaseLost):
        heartbeat(queued.pk, first.lease_owner)
    heartbeat(queued.pk, second.lease_owner)


def test_retry_transient_failure_reuses_run():
    failed = process_run(create_import("crossref", {}).pk, client=Pages(failure=True))
    assert failed.status == "failed"
    retried = retry_run(failed.pk)
    assert retry_run(failed.pk).pk == retried.pk
    done = process_run(retried.pk, client=Pages())
    assert done.status == "succeeded" and ImportRun.objects.count() == 1
    assert not ImportFailure.objects.filter(run=done, resolved=False).exists()


def test_idempotency_conflict_and_profile_path_rejected():
    first = create_import("crossref", {}, "test")
    assert create_import("crossref", {}, "test").pk == first.pk
    with pytest.raises(ImportConflict):
        create_import("openalex", {}, "test")
    with pytest.raises(ValueError):
        create_import("crossref", {"path": "/etc/passwd"})


def test_disabled_external_acquisition_never_calls_transport(settings):
    settings.EXTERNAL_IMPORTS_ENABLED = False

    class Never:
        def page(self, *args):
            pytest.fail("Transport must not be called")

    result = process_run(create_import("crossref", {}).pk, client=Never())
    assert result.status == "failed"
    assert result.failures.get().code == "external_disabled"


def test_malformed_authors_are_terminal_per_record():
    class Malformed:
        def page(self, *args):
            return (
                [
                    {
                        "external_id": "bad",
                        "raw": {"title": "Bad author", "authorships": [{"author": 9}]},
                    },
                    {"external_id": "good", "raw": {"title": "Valid author", "authorships": []}},
                ],
                {"offset": 2},
                True,
            )

    result = process_run(create_import("openalex", {}).pk, client=Malformed())
    assert result.status == "partially_failed"
    assert result.counters == {"read": 2, "rejected": 1, "created": 1}


def test_retry_after_persisted_and_enforced():
    class Throttled:
        def page(self, *args):
            raise ConnectorError("rate_limit", "Wait", retry_after=120)

    result = process_run(create_import("openalex", {}).pk, client=Throttled())
    assert result.cursor["not_before"] > timezone.now().isoformat()
    with pytest.raises(ImportConflict):
        retry_run(result.pk)
    # Even a pre-queued run is ineligible until the persisted provider deadline.
    ImportRun.objects.filter(pk=result.pk).update(status="queued")
    assert claim_run(result.pk) is None


def test_oversized_identifier_failure_does_not_poison_page():
    long_id = "x" * 513

    class Oversized:
        def page(self, *args):
            return (
                [
                    {"external_id": long_id, "raw": {"title": "Invalid identifier"}},
                    {"external_id": "valid", "raw": {"title": "Valid identifier"}},
                ],
                {"offset": 2},
                True,
            )

    result = process_run(create_import("crossref", {}).pk, client=Oversized())
    assert result.status == "partially_failed"
    assert result.counters == {"read": 2, "rejected": 1, "created": 1}
    failure = result.failures.get()
    assert failure.external_id.startswith("invalid-id:sha256:")
    assert len(failure.external_id) < 512
    assert failure.raw["invalid_external_id"] == long_id
    assert SourceRecord.objects.count() == 1


def test_worker_hard_process_exit_resumes_without_duplicates(settings):
    import os
    import subprocess
    import sys

    from django.db import connection

    # The child must use this dedicated pytest database, never the development DB.
    db = connection.settings_dict
    assert db["NAME"].startswith("test_")
    env = os.environ.copy()
    for env_name, db_name in [
        ("PGDATABASE", "NAME"),
        ("PGUSER", "USER"),
        ("PGPASSWORD", "PASSWORD"),
        ("PGHOST", "HOST"),
        ("PGPORT", "PORT"),
    ]:
        env[env_name] = str(db[db_name])
    run = create_import("crossref", {"fixture": "demo", "max_records": 3})
    result = subprocess.run(
        [
            sys.executable,
            str(settings.BASE_DIR / "manage.py"),
            "worker",
            "--once",
            "--run-id",
            str(run.pk),
            "--crash-after",
            "2",
            "--expire-lease",
            "--hard-crash",
        ],
        cwd=settings.BASE_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 137, result.stderr
    run.refresh_from_db()
    assert run.status == "running" and run.cursor.get("offset", 0) == 0
    assert len(run.cursor["pending"]) == 2
    assert SourceRecord.objects.count() == SourceRecordVersion.objects.count() == 2
    done = process_run(run.pk)
    assert done.status == "succeeded"
    assert done.counters == {"read": 3, "created": 3}
    assert SourceRecord.objects.count() == SourceRecordVersion.objects.count() == 3
