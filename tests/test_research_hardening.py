from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.db import close_old_connections, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from research import ai, jobs
from research.commands import CommandError, apply_command
from research.heartbeat import refresh
from research.limits import LimitExceeded, admit_job, consume
from research.models import Dossier, UsageBucket

pytestmark = pytest.mark.django_db


def test_login_attempts_are_limited_by_account_even_when_address_changes(client, settings):
    settings.LOGIN_ATTEMPTS_PER_WINDOW = 2
    for address in ["192.0.2.1", "192.0.2.2"]:
        assert (
            client.post(
                "/accounts/login/",
                {"username": "unknown", "password": "wrong"},
                REMOTE_ADDR=address,
            ).status_code
            == 200
        )
    response = client.post(
        "/accounts/login/", {"username": "unknown", "password": "wrong"}, REMOTE_ADDR="192.0.2.3"
    )
    assert response.status_code == 429
    assert int(response["Retry-After"]) > 0


def test_expired_limit_recovers_and_rejection_does_not_increment():
    consume("test", "identity", 1, 60)
    with pytest.raises(LimitExceeded):
        consume("test", "identity", 1, 60)
    assert UsageBucket.objects.get().count == 1
    UsageBucket.objects.update(started_at=timezone.now() - timedelta(seconds=61))
    consume("test", "identity", 1, 60)
    assert UsageBucket.objects.get().count == 1


def test_queue_limits_reject_without_mutating_dossier(client, settings, monkeypatch):
    user = User.objects.create_user("reviewer")
    client.force_login(user)
    settings.RESEARCH_MAX_ACTIVE_PER_USER = 1
    Dossier.objects.create(owner=user, question="An active task")
    draft = Dossier.objects.create(owner=user, question="A saved draft", status="draft")
    response = client.post(
        reverse("research:action", args=[draft.pk]), {"action": "start", "queries": "tracking"}
    )
    assert response.status_code == 429
    draft.refresh_from_db()
    assert draft.status == "draft" and draft.plan == {}
    monkeypatch.setattr(ai, "availability", lambda: (True, "available"))
    response = client.post(
        "/", {"question": "Another research question", "year_from": 2020, "limit": 5}
    )
    assert response.status_code == 429
    assert Dossier.objects.count() == 2


def test_daily_job_budget_and_global_queue_limit(settings):
    user = User.objects.create_user("reader")
    settings.RESEARCH_DAILY_JOBS = 1
    with transaction.atomic():
        admit_job(user.pk)
    with pytest.raises(LimitExceeded), transaction.atomic():
        admit_job(user.pk)
    settings.RESEARCH_MAX_ACTIVE_GLOBAL = 1
    Dossier.objects.create(owner=user, question="Occupied")
    other = User.objects.create_user("other")
    with pytest.raises(LimitExceeded, match="queue is full"), transaction.atomic():
        admit_job(other.pk)


def test_stop_remains_possible_when_write_limit_exhausted(client, settings):
    user = User.objects.create_user("reader")
    client.force_login(user)
    settings.USER_WRITES_PER_MINUTE = 1
    consume("user-writes", user.pk, 1, 60)
    dossier = Dossier.objects.create(owner=user, question="Stop this task")
    response = client.post(reverse("research:action", args=[dossier.pk]), {"action": "stop"})
    assert response.status_code == 302
    dossier.refresh_from_db()
    assert dossier.status == "cancelled"


def test_lightweight_list_and_status_do_not_load_source_json(client, monkeypatch):
    owner = User.objects.create_user("reader")
    client.force_login(owner)
    dossier = Dossier.objects.create(owner=owner, question="Only metadata", status="ready")
    monkeypatch.setattr(ai, "availability", lambda: (False, "disabled"))
    for url in ["/", reverse("research:status", args=[dossier.pk])]:
        with CaptureQueriesContext(connection) as captured:
            assert client.get(url).status_code == 200
        queries = [q["sql"] for q in captured if 'FROM "research_dossier"' in q["sql"]]
        assert queries
        assert all('"papers"' not in q and '"versions"' not in q for q in queries)


def test_progress_updates_only_changed_columns_and_heartbeat_respects_fencing():
    owner = User.objects.create_user("reader")
    dossier = Dossier.objects.create(owner=owner, question="Lease", status="running")
    with CaptureQueriesContext(connection) as captured:
        jobs.save_progress(dossier.pk, dossier.run_id, "Working")
    assert all('"papers"' not in q["sql"] and '"versions"' not in q["sql"] for q in captured)
    assert refresh(dossier.pk, dossier.run_id) == 1
    Dossier.objects.filter(pk=dossier.pk).update(status="cancelled")
    assert refresh(dossier.pk, dossier.run_id) == 0


def test_command_service_checks_ownership():
    owner = User.objects.create_user("owner")
    other = User.objects.create_user("other")
    dossier = Dossier.objects.create(owner=owner, question="Private")
    with pytest.raises(CommandError, match="does not belong"):
        apply_command(dossier, other, {"action": "stop"}, lambda user: (True, ""))
    dossier.refresh_from_db()
    assert dossier.status == "queued"


def test_search_limit_prevents_retrieval(client, settings):
    owner = User.objects.create_user("reader")
    client.force_login(owner)
    dossier = Dossier.objects.create(owner=owner, question="Search", status="ready")
    settings.USER_SEARCHES_PER_MINUTE = 1
    consume("user-search", owner.pk, 1, 60)
    with patch("research.passage_search.search") as search:
        response = client.get(
            reverse("research:detail", args=[dossier.pk]), {"tab": "passages", "q": "latency"}
        )
        assert response.status_code == 429
        search.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_database_limit_serializes_parallel_process_connections():
    def attempt(_):
        close_old_connections()
        try:
            consume("parallel", "shared", 2, 60)
            return True
        except LimitExceeded:
            return False
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(attempt, range(8))) == 2
    assert UsageBucket.objects.get().count == 2


def test_head_search_is_also_limited(client, settings):
    user = User.objects.create_user("reader")
    client.force_login(user)
    dossier = Dossier.objects.create(owner=user, question="Search", status="ready")
    settings.USER_SEARCHES_PER_MINUTE = 1
    consume("user-search", user.pk, 1, 60)
    with patch("research.passage_search.search") as search:
        response = client.head(
            reverse("research:detail", args=[dossier.pk]), {"tab": "passages", "q": "latency"}
        )
        assert response.status_code == 429
        search.assert_not_called()


def test_deleted_job_is_cancelled_without_crashing_worker():
    owner = User.objects.create_user("reader")
    dossier = Dossier.objects.create(owner=owner, question="Removed during execution", stage="plan")
    claimed = jobs.claim()
    dossier.delete()
    jobs.execute(claimed)


def test_command_service_reloads_stale_state_under_lock():
    owner = User.objects.create_user("reader")
    dossier = Dossier.objects.create(owner=owner, question="Saved draft", status="draft")
    Dossier.objects.filter(pk=dossier.pk).update(status="running")
    with pytest.raises(CommandError, match="already running"):
        apply_command(
            dossier, owner, {"action": "start", "queries": "tracking"}, lambda u: (True, "")
        )


def test_ai_availability_does_not_spawn_on_every_page(settings, monkeypatch):
    from types import SimpleNamespace

    settings.DEBUG = True
    settings.RESEARCH_CODEX_ENABLED = True
    ai._cached_status.cache_clear()
    monkeypatch.setattr(ai.time, "monotonic", lambda: 90)
    with patch(
        "research.ai.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stdout="Logged in using ChatGPT", stderr=""),
    ) as run:
        assert ai.availability()[0]
        assert ai.availability()[0]
        assert run.call_count == 1
    ai._cached_status.cache_clear()


@pytest.mark.django_db(transaction=True)
def test_queue_admission_is_atomic_under_concurrent_requests(settings):
    settings.RESEARCH_MAX_ACTIVE_GLOBAL = 1
    users = [User.objects.create_user(f"reader-{i}").pk for i in range(4)]

    def enqueue(owner_id):
        close_old_connections()
        try:
            with transaction.atomic():
                admit_job(owner_id)
                Dossier.objects.create(owner_id=owner_id, question="Concurrent queue request")
            return True
        except LimitExceeded:
            return False
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(enqueue, users)) == 1
    assert Dossier.objects.filter(status="queued").count() == 1


@pytest.mark.parametrize("method", ["options", "patch", "put", "delete", "post"])
def test_search_page_rejects_non_read_methods(client, method):
    owner = User.objects.create_user("reader")
    client.force_login(owner)
    dossier = Dossier.objects.create(owner=owner, question="Read only", status="ready")
    url = reverse("research:detail", args=[dossier.pk]) + "?tab=passages&q=latency"
    with patch("research.passage_search.search") as search:
        assert getattr(client, method)(url).status_code == 405
        search.assert_not_called()
