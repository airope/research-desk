import copy
from unittest.mock import patch

import httpx
import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from research import ai, inspire, jobs
from research.models import Dossier

PAPER = {
    "id": "123",
    "title": "Particle tracking methods",
    "authors": ["A. Scientist"],
    "year": 2024,
    "doi": "10.1234/example",
    "abstract": "We present a graph neural network for particle tracking. The study uses simulated detector data.",
    "source_url": "https://inspirehep.net/literature/123",
    "fulltext_url": "",
    "references": [],
}
QUOTE = "We present a graph neural network for particle tracking."
REPORT = {
    "summary": "The selected abstract describes graph neural networks.",
    "findings": [
        {
            "heading": "Approach",
            "text": "Graph neural networks are studied.",
            "evidence": [{"paper_id": "123", "quote": QUOTE}],
        }
    ],
    "comparison": [
        {
            "paper_id": "123",
            "method": "Graph neural network",
            "result": "Not reported",
            "limitations": "Not reported",
            "evidence": [{"paper_id": "123", "quote": QUOTE}],
        }
    ],
    "limitations": ["Abstract-only review."],
}


def test_report_rejects_unknown_sources_and_invented_quotes():
    assert (
        ai.validate_report(copy.deepcopy(REPORT), [PAPER])["comparison"][0]["title"]
        == PAPER["title"]
    )
    for key, value in [
        ("paper_id", "999"),
        ("quote", "A fabricated quotation not in this abstract."),
    ]:
        report = copy.deepcopy(REPORT)
        report["findings"][0]["evidence"][0][key] = value
        with pytest.raises(ai.AIError):
            ai.validate_report(report, [PAPER])


def test_report_rejects_cross_paper_comparison_and_empty_evidence():
    report = copy.deepcopy(REPORT)
    report["comparison"][0]["paper_id"] = "456"
    with pytest.raises(ai.AIError):
        ai.validate_report(report, [PAPER, {**PAPER, "id": "456"}])
    report = copy.deepcopy(REPORT)
    report["findings"][0]["evidence"] = []
    with pytest.raises(ai.AIError):
        ai.validate_report(report, [PAPER])


def test_ai_disabled_in_production(settings):
    settings.DEBUG = False
    settings.RESEARCH_CODEX_ENABLED = True
    with patch("research.ai.subprocess.run") as run:
        assert not ai.availability()[0]
        run.assert_not_called()


def test_cli_environment_excludes_api_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "never-forward-this")
    monkeypatch.setenv("CODEX_API_KEY", "never-forward-this")
    assert "OPENAI_API_KEY" not in ai._env()
    assert "CODEX_API_KEY" not in ai._env()


def test_inspire_extracts_abstract_and_constructs_safe_links():
    payload = {
        "hits": {
            "hits": [
                {
                    "id": "123",
                    "metadata": {
                        "titles": [{"title": "Tracking"}],
                        "abstracts": [{"source": "arXiv", "value": "<p>Useful abstract.</p>"}],
                        "authors": [{"full_name": "Scientist, A"}],
                        "preprint_date": "2024-01-01",
                        "arxiv_eprints": [{"value": "2401.12345"}],
                        "references": [
                            {"record": {"$ref": "https://inspirehep.net/api/literature/42"}}
                        ],
                    },
                }
            ]
        }
    }
    with httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=payload))
    ) as client:
        paper = inspire.search("tracking", client=client)[0]
        assert paper["abstract"] == "Useful abstract."
        assert paper["fulltext_url"] == "https://arxiv.org/pdf/2401.12345"
        assert paper["references"] == ["42"]


def test_inspire_limit_errors_and_malformed_response():
    with pytest.raises(inspire.SearchError):
        inspire.search("tracking", limit=999)
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(429))) as client:
        with pytest.raises(inspire.SearchError, match="rate limiting"):
            inspire.search("tracking", client=client)
    with httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    ) as client:
        with pytest.raises(inspire.SearchError):
            inspire.search("tracking", client=client)


@pytest.mark.django_db
def test_dossier_end_to_end_and_exports(client, settings, monkeypatch):
    user = User.objects.create_user("reviewer")
    client.force_login(user)
    monkeypatch.setattr(ai, "availability", lambda: (True, "Local subscription"))
    monkeypatch.setattr(
        ai,
        "generate_plan",
        lambda *a: {"scope": "Tracking approaches", "queries": ["tracking", "graph networks"]},
    )
    monkeypatch.setattr(inspire, "search", lambda *a, **kw: [copy.deepcopy(PAPER)])
    monkeypatch.setattr(ai, "synthesize", lambda *a: copy.deepcopy(REPORT))
    response = client.post(
        reverse("research:home"),
        {"question": "Compare particle tracking methods", "year_from": 2020, "limit": 6},
    )
    assert response.status_code == 302
    dossier = Dossier.objects.get()
    jobs.execute(jobs.claim())
    dossier.refresh_from_db()
    assert dossier.status == "draft"
    response = client.post(
        reverse("research:action", args=[dossier.pk]),
        {"action": "start", "queries": "tracking\ngraph networks"},
    )
    assert response.status_code == 302
    jobs.execute(jobs.claim())
    dossier.refresh_from_db()
    assert dossier.status == "ready", dossier.error
    assert len(dossier.papers) == 1  # repeated searches deduplicated
    assert dossier.report
    page = client.get(
        reverse("research:detail", args=[dossier.pk]), {"tab": "report", "paper": "123"}
    )
    assert page.status_code == 200
    assert QUOTE.encode() in page.content
    for kind in ["md", "bib", "html"]:
        response = client.get(reverse("research:export", args=[dossier.pk]), {"format": kind})
        assert response.status_code == 200
        assert b"123" in response.content
    client.post(
        reverse("research:action", args=[dossier.pk]),
        {"action": "select", "paper_id": "123", "selected": "0"},
    )
    dossier.refresh_from_db()
    assert dossier.report_stale


@pytest.mark.django_db
def test_owner_isolation_and_subscription_guard(client, monkeypatch):
    owner = User.objects.create_user("reviewer")
    outsider = User.objects.create_user("other")
    dossier = Dossier.objects.create(owner=owner, question="Private research question")
    client.force_login(outsider)
    for name in ["detail", "export", "status"]:
        assert client.get(reverse("research:" + name, args=[dossier.pk])).status_code == 404
    assert (
        client.post(reverse("research:action", args=[dossier.pk]), {"action": "stop"}).status_code
        == 404
    )
    other = Dossier.objects.create(
        owner=outsider,
        question="Other question",
        papers=[PAPER],
        selected=["123"],
        stage="synthesize",
    )
    with patch("research.ai.synthesize") as synthesize:
        # Consume the owner's queue first, then claim the other job directly.
        dossier.status = "cancelled"
        dossier.save()
        jobs.execute(jobs.claim())
        synthesize.assert_not_called()
    other.refresh_from_db()
    assert other.status == "failed"


@pytest.mark.django_db
def test_cancellation_fences_late_results_and_duplicate_start(client):
    user = User.objects.create_user("reviewer")
    client.force_login(user)
    dossier = Dossier.objects.create(owner=user, question="Tracking methods")
    running = jobs.claim()
    client.post(
        reverse("research:action", args=[dossier.pk]), {"action": "start", "queries": "tracking"}
    )
    dossier.refresh_from_db()
    assert dossier.run_id == running.run_id
    client.post(reverse("research:action", args=[dossier.pk]), {"action": "stop"})
    with pytest.raises(jobs.Cancelled):
        jobs.save_progress(dossier.pk, running.run_id, "Late result", report=REPORT)
    dossier.refresh_from_db()
    assert not dossier.report


@pytest.mark.django_db
def test_quota_failure_preserves_papers_and_can_regenerate(monkeypatch):
    owner = User.objects.create_user("reviewer")
    dossier = Dossier.objects.create(
        owner=owner, question="Tracking methods", stage="search", plan={"queries": ["tracking"]}
    )
    monkeypatch.setattr(inspire, "search", lambda *a, **kw: [PAPER])

    def no_quota(*args):
        raise ai.AIError("Your Codex allowance is currently exhausted.")

    monkeypatch.setattr(ai, "synthesize", no_quota)
    jobs.execute(jobs.claim())
    dossier.refresh_from_db()
    assert dossier.status == "failed"
    assert dossier.papers == [PAPER]
    assert "allowance" in dossier.error
    assert not dossier.report


@pytest.mark.django_db
def test_manual_search_works_without_ai(client, monkeypatch):
    user = User.objects.create_user("reviewer")
    client.force_login(user)
    monkeypatch.setattr(ai, "availability", lambda: (False, "No allowance"))
    client.post(
        reverse("research:home"),
        {"question": "Compare tracking methods", "year_from": 2020, "limit": 3},
    )
    dossier = Dossier.objects.get()
    assert dossier.status == "draft"
    response = client.get(reverse("research:detail", args=[dossier.pk]))
    assert response.status_code == 200
    assert b"INSPIRE queries" in response.content
    client.post(
        reverse("research:action", args=[dossier.pk]), {"action": "start", "queries": "tracking"}
    )
    dossier.refresh_from_db()
    assert dossier.stage == "search" and dossier.status == "queued"


def test_source_highlighting_preserves_text_and_combines_overlapping_quotes():
    from research.evidence import passages

    report = copy.deepcopy(REPORT)
    parts = passages(PAPER["abstract"], report, "123")
    assert "".join(p["text"] for p in parts) == PAPER["abstract"]
    assert [p["text"] for p in parts if p["quoted"]] == [QUOTE]
    assert not any(p["quoted"] for p in passages(PAPER["abstract"], report, "other"))
