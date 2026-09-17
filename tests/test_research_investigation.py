import copy
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from research import ai, investigation, investigator, jobs
from research.models import Dossier
from tests.test_research import PAPER, REPORT


def decision(action="finish", **kwargs):
    return (
        dict(
            action=action,
            reason="Find the missing measured performance.",
            query="",
            paper_id="",
            reference_id="",
            page=0,
        )
        | kwargs
    )


@pytest.mark.parametrize(
    "value",
    [
        decision("shell"),
        decision("search", query=""),
        decision("read_pdf", paper_id="999"),
        decision("reference", paper_id="123", reference_id="666"),
    ],
)
def test_untrusted_actions_are_rejected(value):
    with pytest.raises(ai.AIError):
        investigator.validate(value, [PAPER])


@pytest.fixture
def dossier(db, monkeypatch):
    owner = User.objects.create_user("reviewer")
    monkeypatch.setattr(ai, "availability", lambda: (True, ""))
    return Dossier.objects.create(
        owner=owner,
        question="Tracking methods",
        focus="Measured latency results",
        papers=[copy.deepcopy(PAPER)],
        selected=["123"],
        report=copy.deepcopy(REPORT),
        report_selected=["123"],
        report_papers=[copy.deepcopy(PAPER)],
        stage="investigate",
    )


def test_loop_uses_observations_and_preserves_source_history(dossier, monkeypatch):
    actions = iter(
        [
            decision("search", query="particle tracking"),
            decision("passages", query="latency"),
            decision(),
        ]
    )
    observed = []

    def decide(question, papers, evidence, steps):
        observed.append(copy.deepcopy(steps))
        return next(actions)

    monkeypatch.setattr(investigator, "decide", decide)
    monkeypatch.setattr("research.inspire.search", lambda *a, **k: [{**PAPER, "id": "456"}])
    seen = {}

    def synthesize(question, papers):
        seen["papers"] = papers
        return copy.deepcopy(REPORT)

    monkeypatch.setattr(ai, "synthesize", synthesize)
    jobs.execute(jobs.claim())
    dossier.refresh_from_db()
    assert dossier.status == "ready", dossier.error
    assert dossier.selected == ["123", "456"]
    assert "Added 1 papers" in observed[1][0]["observation"]
    assert len(dossier.report["investigation"]["steps"]) == 3
    assert len(dossier.versions[-1]["papers"]) == 1
    assert all("_evidence_passages" in p for p in seen["papers"])
    assert dossier.runs.first().status == "ready"


def test_repeat_action_stops_without_repeating_network(dossier, monkeypatch):
    monkeypatch.setattr(investigator, "decide", lambda *a: decision("search", query="tracking"))
    monkeypatch.setattr(ai, "synthesize", lambda *a: copy.deepcopy(REPORT))
    with patch("research.inspire.search", return_value=[]) as search:
        jobs.execute(jobs.claim())
    assert search.call_count == 1
    dossier.refresh_from_db()
    assert "repeated" in dossier.investigation["stop_reason"]


def test_cancel_during_decision_prevents_action_and_report(dossier, client, monkeypatch):
    client.force_login(dossier.owner)

    def decide(*args):
        client.post(reverse("research:action", args=[dossier.pk]), {"action": "stop"})
        return decision("search", query="tracking")

    monkeypatch.setattr(investigator, "decide", decide)
    with patch("research.inspire.search") as search, patch("research.ai.synthesize") as synth:
        jobs.execute(jobs.claim())
    search.assert_not_called()
    synth.assert_not_called()
    dossier.refresh_from_db()
    assert dossier.status == "cancelled"
    assert dossier.report == REPORT


def test_action_route_and_owner_isolation(dossier, client):
    dossier.status = "ready"
    dossier.save()
    outsider = User.objects.create_user("outsider")
    client.force_login(outsider)
    url = reverse("research:action", args=[dossier.pk])
    assert (
        client.post(
            url, {"action": "investigate", "focus": "Find numerical latency results"}
        ).status_code
        == 404
    )
    client.force_login(dossier.owner)
    assert (
        client.post(
            url, {"action": "investigate", "focus": "Find numerical latency results"}
        ).status_code
        == 302
    )
    dossier.refresh_from_db()
    assert dossier.stage == "investigate" and dossier.status == "queued"


def test_reference_edges_verified_and_exclusions_preserved(dossier):
    papers = [{**PAPER, "references": ["456"]}, {**PAPER, "id": "456"}]
    with patch("research.inspire.search", return_value=[{**PAPER, "id": "456"}]) as search:
        selected = ["123"]
        result = investigation.perform(
            decision("reference", paper_id="123", reference_id="456"),
            papers,
            selected,
            {"123", "456"},
            dossier,
        )
    assert selected == ["123"]
    assert search.call_args.args[0] == "recid:456"
    assert "Added 0" in result


def test_paper_limit_blocks_external_call(dossier):
    papers = [{**PAPER, "id": str(i)} for i in range(20)]
    with patch("research.inspire.search") as search:
        result = investigation.perform(
            decision("search", query="tracking"), papers, [], set(), dossier
        )
    search.assert_not_called()
    assert "limit reached" in result


def test_final_synthesis_uses_collected_passages_without_reranking(monkeypatch):
    evidence = [
        {
            **PAPER,
            "_evidence_passages": [{"page": 0, "text": PAPER["abstract"]}],
            "_retrieval": {"engine": "local-keywords", "warning": ""},
        }
    ]
    monkeypatch.setattr(ai, "_request", lambda *a: copy.deepcopy(REPORT))
    with patch("research.ai.select_evidence") as select:
        result = ai.synthesize("Tracking", evidence)
    select.assert_not_called()
    assert result["retrieval"]["passages"][0]["text"] == PAPER["abstract"]


def test_three_action_budget_is_enforced(dossier, monkeypatch):
    decisions = iter([decision("passages", query=f"latency {i}") for i in range(3)])
    calls = []

    def decide(*args):
        calls.append(1)
        return next(decisions)

    monkeypatch.setattr(investigator, "decide", decide)
    monkeypatch.setattr(ai, "synthesize", lambda *a: copy.deepcopy(REPORT))
    jobs.execute(jobs.claim())
    dossier.refresh_from_db()
    assert len(calls) == 3
    assert dossier.investigation["stop_reason"] == "The three-action budget was reached."


def test_citations_query_uses_verified_parent_and_date(dossier):
    with patch("research.inspire.search", return_value=[]) as search:
        investigation.perform(
            decision("citations", paper_id="123"), [PAPER], ["123"], {"123"}, dossier
        )
    assert search.call_args.args[0] == "(refersto:recid:123) and date > 2019"


def test_observation_is_retained_after_search_failure(dossier, monkeypatch):
    from research.inspire import SearchError

    decisions = iter([decision("search", query="tracking"), decision()])
    monkeypatch.setattr(investigator, "decide", lambda *a: next(decisions))
    monkeypatch.setattr(ai, "synthesize", lambda *a: copy.deepcopy(REPORT))
    with patch(
        "research.inspire.search", side_effect=SearchError("INSPIRE is rate limiting requests.")
    ):
        jobs.execute(jobs.claim())
    dossier.refresh_from_db()
    assert dossier.status == "ready"
    assert dossier.investigation["steps"][0]["status"] == "failed"
    assert "rate limiting" in dossier.investigation["steps"][0]["observation"]


def test_read_page_supplies_original_text_without_reranking(dossier, monkeypatch):
    text = "Synthesized latency is 59 cycles with a 5 ns clock. " * 100
    dossier.papers[0]["document"] = {"status": "available", "pages": [{"page": 20, "text": text}]}
    dossier.save()
    decisions = iter([decision("read_page", paper_id="123", page=20), decision()])
    monkeypatch.setattr(investigator, "decide", lambda *a: next(decisions))
    seen = {}

    def synthesize(question, evidence):
        seen["evidence"] = evidence
        return copy.deepcopy(REPORT)

    monkeypatch.setattr(ai, "synthesize", synthesize)
    jobs.execute(jobs.claim())
    dossier.refresh_from_db()
    assert dossier.status == "ready", dossier.error
    passage = seen["evidence"][0]["_evidence_passages"][0]
    assert passage == {"page": 20, "text": text[:4000]}
    assert "Read PDF page 20" in dossier.report["investigation"]["steps"][0]["observation"]


def test_unavailable_page_is_rejected():
    with pytest.raises(ai.AIError, match="unavailable PDF page"):
        investigator.validate(decision("read_page", paper_id="123", page=20), [PAPER])
