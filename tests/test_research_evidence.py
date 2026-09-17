import copy
import json

import pytest

from research import ai
from research.retrieval import select_evidence

QUOTE = "Graph neural networks reduce reconstruction latency on simulated detector events."
PAPER = {
    "id": "101",
    "title": "Tracking",
    "abstract": "This study reviews particle detectors and their reconstruction methods.",
    "document": {
        "status": "available",
        "pages": [
            {"page": 1, "text": "Background information about facilities. " * 100},
            {"page": 2, "text": QUOTE},
        ],
    },
}


def report(page=2, quote=QUOTE):
    evidence = {"paper_id": "101", "page": page, "quote": quote}
    return {
        "summary": "Reconstruction latency is studied.",
        "findings": [{"heading": "Latency", "text": "Latency is studied.", "evidence": [evidence]}],
        "comparison": [
            {
                "paper_id": "101",
                "method": "Graph neural networks",
                "result": "Reduced latency",
                "limitations": "Simulated events",
                "evidence": [dict(evidence)],
            }
        ],
        "limitations": [],
    }


def test_retrieval_selects_relevant_late_page_within_global_budget():
    paper = copy.deepcopy(PAPER)
    paper["document"]["pages"] += [
        {"page": 20, "text": "Specific quantum calibration fidelity measurements. " * 50}
    ]
    result = select_evidence("quantum calibration fidelity", [paper])
    assert result[0]["_evidence_passages"][1]["page"] == 20
    many = select_evidence("quantum calibration fidelity", [paper] * 25)
    assert len(many) == 20
    assert sum(len(p["text"]) for row in many for p in row["_evidence_passages"]) <= 80_000
    assert all(len([p for p in row["_evidence_passages"] if p["page"] > 0]) <= 5 for row in many)


def test_fulltext_without_abstract_is_supported_and_coverage_is_computed():
    paper = {**PAPER, "abstract": ""}
    result = ai.validate_report(report(), [paper])
    assert result["coverage"]["fulltext_papers"] == 1
    assert result["coverage"]["abstract_only_papers"] == 0
    assert result["evidence_sources"]["101"] == {"pages": [2], "kind": "fulltext"}
    assert "not an exhaustive reading" in result["limitations"][-1]


@pytest.mark.parametrize("page", [1, 3, -1, True, "2"])
def test_quote_rejected_on_wrong_or_nonexistent_page(page):
    with pytest.raises(ai.AIError):
        ai.validate_report(report(page=page), [PAPER])


def test_cross_page_quote_is_rejected():
    paper = copy.deepcopy(PAPER)
    paper["document"]["pages"] = [
        {"page": 1, "text": "Graph neural networks reduce"},
        {"page": 2, "text": "reconstruction latency on simulated detector events."},
    ]
    with pytest.raises(ai.AIError):
        ai.validate_report(report(page=1), [paper])


def test_selected_evidence_does_not_allow_hidden_text_or_disjoint_chunks():
    paper = {
        **PAPER,
        "_evidence_passages": [
            {"page": 2, "text": "Graph neural networks reduce"},
            {"page": 2, "text": "reconstruction latency on simulated detector events."},
        ],
    }
    with pytest.raises(ai.AIError):
        ai.validate_report(report(), [paper])


def test_synthesis_validates_only_text_actually_sent(monkeypatch):
    paper = copy.deepcopy(PAPER)
    hidden = "Unrelated hidden sentence outside the selected evidence window."
    paper["abstract"] = ("Background overview. " * 100) + hidden
    seen = {}

    def fake_request(prompt, schema):
        seen["prompt"] = prompt
        return report(page=0, quote=hidden)

    monkeypatch.setattr(ai, "_request", fake_request)
    with pytest.raises(ai.AIError):
        ai.synthesize("graph neural networks latency", [paper])
    assert hidden not in seen["prompt"]
    payload = json.loads(seen["prompt"].split("\n", 1)[1])
    assert payload["papers"][0]["_evidence_passages"][1]["page"] == 2


def test_legacy_abstract_quote_defaults_to_zero():
    quote = PAPER["abstract"]
    value = report(page=0, quote=quote)
    for row in value["findings"] + value["comparison"]:
        del row["evidence"][0]["page"]
    result = ai.validate_report(value, [{**PAPER, "document": {}}])
    assert result["findings"][0]["evidence"][0]["page"] == 0
    assert result["coverage"]["abstract_only_papers"] == 1


def test_followup_query_drives_retrieval_without_losing_model_context(monkeypatch):
    from research import retrieval

    seen = {}

    def select(query, papers):
        seen["query"] = query
        return retrieval.select_evidence(query, papers)

    def request(prompt, schema):
        seen["prompt"] = prompt
        return report()

    monkeypatch.setattr(ai, "select_evidence", select)
    monkeypatch.setattr(ai, "_request", request)
    result = ai.synthesize(
        "Broad research context", [{**PAPER, "_search_query": "reconstruction latency"}]
    )
    assert seen["query"] == "reconstruction latency"
    assert "Broad research context" in seen["prompt"]
    assert result["retrieval"]["query"] == "reconstruction latency"
