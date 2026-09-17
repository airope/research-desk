import csv
import io

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from catalogues import services
from catalogues.models import Catalogue, Entry, Selection
from records.models import SourceRecord
from records.normalization import normalize_record

pytestmark = pytest.mark.django_db


def account(name):
    return User.objects.create_user(name, password="local-workflow-test")


def upload(
    client, content=b"local_id,title,doi,year\nLAB-1,An actual test title,10.1234/testing,2025\n"
):
    response = client.post(
        reverse("catalogues:new"),
        {
            "name": "My laboratory catalogue",
            "source": "csv",
            "file": SimpleUploadedFile("catalogue.csv", content, content_type="text/csv"),
        },
    )
    assert response.status_code == 302, response.content
    draft = Selection.objects.latest("created_at")
    response = client.post(
        reverse("catalogues:preview", args=[draft.pk]),
        {
            "expected_revision": draft.catalogue.revision,
        },
    )
    assert response.status_code == 302, response.content
    return Catalogue.objects.get(pk=draft.catalogue_id)


def incoming_snapshot():
    raw = {
        "title": "An actual test title",
        "DOI": "10.1234/testing",
        "year": 2025,
        "journal": "Journal of tests",
    }
    return {
        "source": "inspire",
        "external_id": "123456",
        "local_id": "",
        "raw": raw,
        "normalized": {**normalize_record("inspire", raw), "journal": "Journal of tests"},
    }


def test_browser_workflow_upload_search_merge_correct_and_export(client, monkeypatch):
    client.force_login(account("librarian"))
    catalogue = upload(client)
    assert catalogue.entries.count() == 1
    assert SourceRecord.objects.count() == 0
    baseline = catalogue.entries.get()
    assert baseline.local_id == "LAB-1"
    from catalogues import acquisition

    monkeypatch.setattr(
        acquisition,
        "search_inspire",
        lambda filters: {
            "rows": [incoming_snapshot()],
            "errors": [],
            "total": 1,
            "truncated": False,
            "query": "collaboration:ATLAS and jy 2025",
        },
    )
    response = client.post(
        reverse("catalogues:selection", args=[catalogue.pk]),
        {
            "source": "inspire",
            "collaboration": "ATLAS",
            "year_from": 2025,
            "year_to": 2025,
            "type": "articles",
            "limit": 10,
        },
    )
    assert response.status_code == 302, response.content
    draft = catalogue.selections.filter(kind="incoming").get()
    preview_url = reverse("catalogues:preview", args=[draft.pk])
    assert client.get(preview_url).status_code == 200
    catalogue.refresh_from_db()
    payload = {"expected_revision": catalogue.revision}
    assert client.post(preview_url, payload).status_code == 302
    assert client.post(preview_url, payload).status_code == 302
    assert catalogue.entries.count() == 2
    incoming = catalogue.entries.get(origin="incoming")
    catalogue.refresh_from_db()
    entry_url = reverse("catalogues:entry", args=[incoming.pk])
    assert client.get(entry_url).status_code == 200
    response = client.post(
        entry_url,
        {
            "action": "merge",
            "target_id": str(baseline.pk),
            "expected_revision": catalogue.revision,
            "idempotency_key": "merge-test",
            "reason": "Reviewed matching title and DOI.",
        },
    )
    assert response.status_code == 302, response.content
    incoming.refresh_from_db()
    assert incoming.status == "merged"
    catalogue.refresh_from_db()
    response = client.post(
        reverse("catalogues:entry", args=[baseline.pk]),
        {
            "operation": "edit",
            "title": "A corrected test title",
            "doi": "10.1234/testing",
            "year": 2025,
            "journal": "Journal of tests",
            "reason": "Confirmed source title",
            "expected_revision": catalogue.revision,
            "idempotency_key": "correction-test",
        },
    )
    assert response.status_code == 302, response.content
    response = client.post(
        reverse("catalogues:export", args=[catalogue.pk]),
        {"format": "catalogue", "unresolved": "exclude"},
    )
    assert response.status_code == 200
    assert "attachment" in response["Content-Disposition"]
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert len(rows) == 1
    assert rows[0]["title"] == "A corrected test title"
    assert "LAB-1" in response.content.decode()
    report = client.post(
        reverse("catalogues:export", args=[catalogue.pk]),
        {"format": "changes", "unresolved": "exclude"},
    )
    assert report.status_code == 200
    assert b"merge" in report.content and b"correct" in report.content
    baseline.refresh_from_db()
    assert baseline.raw["title"] == "An actual test title"
    assert SourceRecord.objects.count() == 0


def test_private_routes_and_exports_are_owner_scoped(client):
    owner = account("owner")
    client.force_login(owner)
    catalogue = upload(client)
    item = catalogue.entries.get()
    draft = catalogue.selections.get()
    urls = [
        reverse("catalogues:detail", args=[catalogue.pk]),
        reverse("catalogues:selection", args=[catalogue.pk]),
        reverse("catalogues:entry", args=[item.pk]),
        reverse("catalogues:preview", args=[draft.pk]),
        reverse("catalogues:export", args=[catalogue.pk]),
    ]
    client.force_login(account("outsider"))
    for url in urls:
        assert client.get(url).status_code == 404, url
        if "/selection/" in url or "/entries/" in url or "/previews/" in url or "/export/" in url:
            assert client.post(url, {}).status_code == 404, url
    assert b"My laboratory catalogue" not in client.get("/").content
    client.logout()
    for url in urls:
        assert client.get(url).status_code == 302
    assert b"An actual test title" not in client.get("/api/v1/publications").content
    assert client.get("/").status_code == 200


def test_partial_csv_preview_requires_acknowledgement(client):
    client.force_login(account("csv-reviewer"))
    response = client.post(
        reverse("catalogues:new"),
        {
            "name": "Partial file",
            "source": "csv",
            "file": SimpleUploadedFile(
                "partial.csv", b"local_id,title,year\n1,Valid row,2025\n2,Invalid year,not-a-year\n"
            ),
        },
    )
    assert response.status_code == 302, response.content
    draft = Selection.objects.get()
    assert draft.errors
    url = reverse("catalogues:preview", args=[draft.pk])
    assert client.post(url, {"expected_revision": draft.catalogue.revision}).status_code == 400
    assert not Entry.objects.exists()
    assert (
        client.post(
            url, {"expected_revision": draft.catalogue.revision, "acknowledge_errors": "yes"}
        ).status_code
        == 302
    )
    assert Entry.objects.count() == 1


def test_csrf_and_malformed_decisions(client):
    owner = account("csrf-user")
    client.force_login(owner)
    catalogue = upload(client)
    entry = catalogue.entries.get()
    url = reverse("catalogues:entry", args=[entry.pk])
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(owner)
    assert strict.post(url, {"action": "exclude"}).status_code == 403
    assert (
        client.post(
            url,
            {"action": "merge", "target_id": "not-a-uuid", "expected_revision": catalogue.revision},
        ).status_code
        == 400
    )
    assert client.post(url, {"action": "keep", "expected_revision": "bad"}).status_code == 400
    entry.refresh_from_db()
    assert entry.status == "kept"


def test_unresolved_export_policy_and_reverse_merge(client):
    owner = account("exporter")
    client.force_login(owner)
    catalogue = upload(client)
    row = incoming_snapshot()
    row["provider"] = row.pop("source")
    draft = services.create_selection(owner, catalogue.pk, "incoming", [row])
    services.confirm_selection(owner, draft.pk, catalogue.revision)
    catalogue.refresh_from_db()
    export_url = reverse("catalogues:export", args=[catalogue.pk])

    def count(mode):
        result = client.post(export_url, {"format": "catalogue", "unresolved": mode})
        assert result.status_code == 200
        return list(csv.DictReader(io.StringIO(result.content.decode("utf-8-sig"))))

    assert len(count("exclude")) == 1
    rows = count("include")
    assert len(rows) == 2
    assert any(row["status"] == "pending" for row in rows)
    incoming = catalogue.entries.get(origin="incoming")
    baseline = catalogue.entries.get(origin="baseline")
    services.decide(owner, incoming.pk, "merge", catalogue.revision, target_id=baseline.pk)
    catalogue.refresh_from_db()
    services.decide(owner, incoming.pk, "reset", catalogue.revision, reason="Reconsider match")
    incoming.refresh_from_db()
    assert incoming.status == "pending"
    assert incoming.merge_target_id is None
    assert len(count("include")) == 2


def test_corrected_doi_search_and_changed_fields_only(client):
    owner = account("corrector")
    client.force_login(owner)
    catalogue = upload(
        client, b"local_id,title,doi,year,journal\nLAB-1,An actual test title,,2025,\n"
    )
    baseline = catalogue.entries.get()
    row = incoming_snapshot()
    row["provider"] = row.pop("source")
    draft = services.create_selection(owner, catalogue.pk, "incoming", [row])
    services.confirm_selection(owner, draft.pk, catalogue.revision)
    catalogue.refresh_from_db()
    incoming = catalogue.entries.get(origin="incoming")
    services.decide(owner, incoming.pk, "merge", catalogue.revision, target_id=baseline.pk)
    catalogue.refresh_from_db()
    # The browser form shows the final projected DOI. Changing only the journal
    # must not convert the untouched inherited DOI into a manual correction.
    response = client.post(
        reverse("catalogues:entry", args=[baseline.pk]),
        {
            "operation": "edit",
            "title": "An actual test title",
            "doi": "10.1234/testing",
            "year": 2025,
            "journal": "Corrected journal",
            "reason": "Checked journal label",
            "expected_revision": catalogue.revision,
            "idempotency_key": "journal-only",
        },
    )
    assert response.status_code == 302, response.content
    baseline.refresh_from_db()
    assert set(baseline.overrides) == {"journal"}
    assert services.projection(baseline)[0]["doi"] == "10.1234/testing"
    catalogue.refresh_from_db()
    services.edit_fields(
        owner, baseline.pk, {"doi": "10.1234/corrected"}, "Correct DOI", catalogue.revision
    )
    response = client.get(
        reverse("catalogues:detail", args=[catalogue.pk]), {"q": "10.1234/corrected"}
    )
    assert response.status_code == 200
    assert baseline.pk in [row.pk for row in response.context["page"]]
