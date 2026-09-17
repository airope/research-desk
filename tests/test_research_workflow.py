import copy

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from research import ai, fulltext, jobs
from research.models import Dossier
from research.reviews import fingerprint

pytestmark = pytest.mark.django_db

PAPER = {"id": "11", "title": "Tracking", "abstract": "Original abstract evidence.", "year": 2024}
REPORT = {
    "summary": "Original report",
    "findings": [{"heading": "Method", "text": "Original finding", "evidence": []}],
    "comparison": [],
    "limitations": [],
}
DOCUMENT = {"status": "available", "pages": [{"page": 1, "text": "Extracted PDF evidence."}]}


@pytest.fixture
def dossier(client, monkeypatch, settings):
    settings.RESEARCH_LOCAL_USER = "reviewer"
    owner = User.objects.create_user("reviewer")
    client.force_login(owner)
    monkeypatch.setattr(ai, "availability", lambda: (True, "Local subscription"))
    return Dossier.objects.create(
        owner=owner,
        question="Compare particle tracking approaches",
        status="ready",
        papers=[copy.deepcopy(PAPER)],
        selected=["11"],
        report=copy.deepcopy(REPORT),
        report_selected=["11"],
        report_papers=[copy.deepcopy(PAPER)],
    )


def action(client, dossier, **data):
    return client.post(reverse("research:action", args=[dossier.pk]), data)


def test_fulltext_run_freezes_old_report_sources_and_records_operations(
    client, dossier, monkeypatch
):
    monkeypatch.setattr(fulltext, "fetch_document", lambda paper: copy.deepcopy(DOCUMENT))
    seen = []

    def synthesize(question, papers):
        seen.extend(copy.deepcopy(papers))
        return {**copy.deepcopy(REPORT), "summary": "New fulltext report"}

    monkeypatch.setattr(ai, "synthesize", synthesize)
    action(client, dossier, action="fulltext")
    jobs.execute(jobs.claim())
    dossier.refresh_from_db()
    assert dossier.status == "ready", dossier.error
    assert seen[0]["document"] == DOCUMENT
    assert dossier.report_papers[0]["document"] == DOCUMENT
    assert "document" not in dossier.versions[0]["papers"][0]
    assert dossier.versions[0]["report"]["summary"] == "Original report"
    run = dossier.runs.get()
    assert run.status == "ready" and run.finished_at is not None
    assert [m["operation"] for m in run.metrics] == ["PDF extraction", "AI synthesis"]
    assert all(m["success"] and m["seconds"] >= 0 for m in run.metrics)


def test_followup_changes_focus_without_rerunning_search(client, dossier, monkeypatch):
    seen = []
    monkeypatch.setattr(
        ai, "synthesize", lambda question, papers: seen.append(question) or copy.deepcopy(REPORT)
    )
    action(client, dossier, action="followup", focus="Compare the computational limitations")
    dossier.refresh_from_db()
    assert dossier.report_stale
    jobs.execute(jobs.claim())
    dossier.refresh_from_db()
    assert "Compare the computational limitations" in seen[0]
    assert dossier.report_focus == dossier.focus
    assert not dossier.report_stale
    assert dossier.versions[0]["focus"] == ""
    assert [m["operation"] for m in dossier.runs.get().metrics] == ["AI synthesis"]


def test_failed_synthesis_retains_report_snapshot_and_extracted_pdf(client, dossier, monkeypatch):
    monkeypatch.setattr(fulltext, "fetch_document", lambda paper: copy.deepcopy(DOCUMENT))

    def exhausted(*args):
        raise ai.AIError("Subscription allowance exhausted")

    monkeypatch.setattr(ai, "synthesize", exhausted)
    action(client, dossier, action="fulltext")
    jobs.execute(jobs.claim())
    dossier.refresh_from_db()
    assert dossier.status == "failed"
    assert dossier.papers[0]["document"] == DOCUMENT
    assert dossier.report == REPORT
    assert dossier.report_papers == [PAPER]
    assert dossier.versions == []
    run = dossier.runs.get()
    assert run.status == "failed"
    assert [m["success"] for m in run.metrics] == [True, False]


def test_review_requires_current_report_token_and_records_owner(client, dossier):
    token = fingerprint(dossier.report)
    action(
        client, dossier, action="review", report_token="outdated", finding="0", verdict="supported"
    )
    dossier.refresh_from_db()
    assert "reviews" not in dossier.report
    action(
        client,
        dossier,
        action="review",
        report_token=token,
        finding="0",
        verdict="uncertain",
        note="Check method section",
    )
    dossier.refresh_from_db()
    assert dossier.report["reviews"]["0"]["actor"] == "reviewer"
    assert dossier.report["reviews"]["0"]["verdict"] == "uncertain"
    assert fingerprint(dossier.report) == token
    dossier.report["summary"] = "Replaced report"
    dossier.save()
    action(client, dossier, action="review", report_token=token, finding="0", verdict="supported")
    dossier.refresh_from_db()
    assert dossier.report["reviews"]["0"]["verdict"] == "uncertain"


def test_new_endpoints_and_commands_are_owner_scoped(client, dossier):
    dossier.versions = [{"report": REPORT, "papers": [PAPER], "focus": "", "selected": ["11"]}]
    dossier.save()
    other = User.objects.create_user("other")
    client.force_login(other)
    assert client.get(reverse("research:version", args=[dossier.pk, 0])).status_code == 404
    for command in ["fulltext", "followup", "review"]:
        assert (
            action(client, dossier, action=command, focus="Computational limitations").status_code
            == 404
        )
    dossier.refresh_from_db()
    assert dossier.status == "ready"


def test_invalid_followup_and_unavailable_subscription_do_not_queue(client, dossier, monkeypatch):
    original_run = dossier.run_id
    action(client, dossier, action="followup", focus="tiny")
    monkeypatch.setattr(ai, "availability", lambda: (False, "Quota unavailable"))
    action(client, dossier, action="fulltext")
    dossier.refresh_from_db()
    assert dossier.run_id == original_run
    assert dossier.status == "ready"
    assert not dossier.use_fulltext


def test_stop_during_synthesis_preserves_previous_report_and_marks_run_cancelled(
    client, dossier, monkeypatch
):
    def stop_then_return(*args):
        action(client, dossier, action="stop")
        return {**REPORT, "summary": "Late result must be discarded"}

    monkeypatch.setattr(ai, "synthesize", stop_then_return)
    action(client, dossier, action="regenerate")
    jobs.execute(jobs.claim())
    dossier.refresh_from_db()
    assert dossier.status == "cancelled"
    assert dossier.report == REPORT
    assert dossier.versions == []
    assert dossier.runs.get().status == "cancelled"


def test_report_source_panel_print_and_version_use_frozen_sources(client, dossier):
    frozen = {
        **PAPER,
        "title": "Frozen source title",
        "document": copy.deepcopy(DOCUMENT),
        "authors": ["A. Scientist"],
        "doi": "",
        "source_url": "https://inspirehep.net/literature/11",
    }
    dossier.report_papers = [frozen]
    dossier.papers = [
        {**frozen, "title": "Changed live title", "document": {"status": "unavailable"}}
    ]
    dossier.report["findings"][0]["evidence"] = [
        {"paper_id": "11", "page": 1, "quote": "Extracted PDF evidence."}
    ]
    dossier.versions = [
        {
            "report": copy.deepcopy(dossier.report),
            "papers": [frozen],
            "focus": "Prior focus",
            "selected": ["11"],
        }
    ]
    dossier.save()
    detail = client.get(
        reverse("research:detail", args=[dossier.pk]), {"tab": "report", "paper": "11", "page": 1}
    )
    assert detail.status_code == 200
    assert detail.context["source_text"] == "Extracted PDF evidence."
    assert detail.context["selected_paper"]["title"] == "Frozen source title"
    for kind in ["html", "md", "bib"]:
        response = client.get(reverse("research:export", args=[dossier.pk]), {"format": kind})
        assert response.status_code == 200
        assert b"Frozen source title" in response.content
        assert b"Changed live title" not in response.content
        if kind != "bib":
            assert b"PDF page 1" in response.content
    version = client.get(reverse("research:version", args=[dossier.pk, 0]))
    assert version.status_code == 200
    assert b"Extracted PDF evidence." in version.content
    assert b"Prior focus" in version.content
    assert client.get(reverse("research:version", args=[dossier.pk, 1])).status_code == 404
