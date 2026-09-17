import uuid

import pytest
from django.contrib.auth.models import Group, User
from django.test import Client

from records.models import CandidatePair, ReviewDecision
from records.services import compare_pair, ingest_record

pytestmark = pytest.mark.django_db


def candidate():
    a = ingest_record(
        "crossref", "api-one", {"title": ["A scientific result"], "DOI": "10.1234/api"}
    )[0]
    b = ingest_record(
        "openalex", "api-two", {"title": "A scientific result", "doi": "10.1234/api"}
    )[0]
    a, b = sorted([a, b], key=lambda record: record.id)
    pair = CandidatePair.objects.create(left=a, right=b)
    compare_pair(pair)
    pair.refresh_from_db()
    return pair


def user(role="curator"):
    value = User.objects.create_user(username=role, password="local-test-password")
    value.groups.add(Group.objects.get_or_create(name=role)[0])
    return value


def test_public_read_and_write_denied(client):
    pair = candidate()
    url = f"/api/v1/candidates/{pair.id}"
    response = client.get(url)
    assert response.status_code == 200
    assert response.json()["proposal"]["left_version"]["raw"]
    response = client.post(
        url + "/decisions",
        {"action": "accept", "expected_revision": pair.revision, "idempotency_key": "denied"},
        content_type="application/json",
    )
    assert response.status_code == 403
    assert {"code", "message", "fields", "request_id"} <= response.json().keys()
    assert ReviewDecision.objects.count() == 0


def test_validation_and_missing_resource(client):
    for query in [
        "page_size=101",
        "page_size=-1",
        "state=bogus",
        "conflict=maybe",
        "source=unknown",
    ]:
        assert client.get("/api/v1/candidates?" + query).status_code == 400
    response = client.get(f"/api/v1/candidates/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["request_id"]


def test_decision_idempotence_stale_revision_and_withdrawal(client):
    pair = candidate()
    client.force_login(user())
    url = f"/api/v1/candidates/{pair.id}/decisions"
    payload = {
        "action": "accept",
        "reason": "",
        "expected_revision": pair.revision,
        "idempotency_key": "network-retry",
    }
    first = client.post(url, payload, content_type="application/json")
    assert first.status_code == 201, first.content
    repeat = client.post(url, payload, content_type="application/json")
    assert repeat.json()["id"] == first.json()["id"]
    payload["idempotency_key"] = "stale"
    assert client.post(url, payload, content_type="application/json").status_code == 409
    withdraw_url = f"/api/v1/decisions/{first.json()['id']}/withdraw"
    preview = client.get(withdraw_url).json()
    assert preview["will_split"]
    response = client.post(
        withdraw_url,
        {
            "reason": "Reviewed again",
            "expected_revision": preview["expected_revision"],
            "idempotency_key": "undo",
        },
        content_type="application/json",
    )
    assert response.status_code == 201


def test_csrf_and_roles():
    pair = candidate()
    client = Client(enforce_csrf_checks=True)
    client.force_login(user())
    response = client.post(
        f"/api/v1/candidates/{pair.id}/decisions", {}, content_type="application/json"
    )
    assert response.status_code == 403
    assert (
        client.post(
            "/accounts/login/", {"username": "curator", "password": "local-test-password"}
        ).status_code
        == 403
    )
    client.get(f"/review/{pair.id}/")
    token = client.cookies["csrftoken"].value
    response = client.post(
        f"/api/v1/candidates/{pair.id}/decisions",
        {
            "action": "defer",
            "reason": "Needs a source check",
            "expected_revision": pair.revision,
            "idempotency_key": "csrf-valid",
        },
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 201, response.content
    assert (
        client.post(
            "/api/v1/imports", {}, content_type="application/json", HTTP_X_CSRFTOKEN=token
        ).status_code
        == 403
    )


def test_html_pages_escape_sources(client):
    pair = candidate()
    ingest_record(
        pair.left.provider,
        pair.left.external_id,
        {"title": ["<script>alert(1)</script>"], "DOI": "10.1234/api"},
    )
    compare_pair(pair.id)
    for url in [
        "/review/",
        f"/review/{pair.id}/",
        "/catalogue/",
        f"/catalogue/{pair.left.publication_id}/",
        "/imports/",
        "/evaluation/",
        "/accounts/login/",
    ]:
        response = client.get(url)
        assert response.status_code == 200, (url, response.content)
        assert b"<script>alert(1)</script>" not in response.content
    assert b"&lt;script&gt;" in client.get(f"/review/{pair.id}/").content


def test_operator_import_profile_restriction_and_idempotence(client):
    client.force_login(user("operator"))
    payload = {"provider": "crossref", "profile": "demo", "idempotency_key": "import-demo"}
    first = client.post("/api/v1/imports", payload, content_type="application/json")
    assert first.status_code == 202, first.content
    repeat = client.post("/api/v1/imports", payload, content_type="application/json")
    assert repeat.json()["id"] == first.json()["id"]
    payload["provider"] = "openalex"
    assert (
        client.post("/api/v1/imports", payload, content_type="application/json").status_code == 409
    )
    payload["profile"] = "/etc/passwd"
    assert (
        client.post("/api/v1/imports", payload, content_type="application/json").status_code == 400
    )


def test_queue_counts_review_states_and_orders_latest_scores(client):
    from records.models import MatchProposal

    first = candidate()
    second_a = ingest_record("crossref", "order-a", {"title": ["Other record"]})[0]
    second_b = ingest_record("openalex", "order-b", {"title": "Other record"})[0]
    left, right = sorted([second_a, second_b], key=lambda record: record.id)
    second = CandidatePair.objects.create(left=left, right=right)
    compare_pair(second)
    # A historical high score must not outrank the latest low score.
    original = second.proposals.first()
    MatchProposal.objects.create(
        pair=second,
        left_version=original.left_version,
        right_version=original.right_version,
        signals={},
        ranking_score=0.1,
        recommendation="review",
    )
    response = client.get("/api/v1/candidates?state=review")
    assert response.status_code == 200
    assert response.json()["results"][0]["id"] == str(first.id)
    response = client.get("/review/")
    assert response.context["stats"]["pending"] == 2
    assert b"Insufficient evidence" in response.content
