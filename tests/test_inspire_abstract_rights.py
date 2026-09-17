import httpx
import pytest

from research.inspire import search


@pytest.mark.parametrize("source", ["arXiv", "CERN"])
def test_mixed_abstract_sources_select_only_permitted_evidence(source):
    paper = retrieve(
        [
            {"source": "Publisher", "value": "Restricted publisher evidence"},
            {"value": "Unknown origin evidence"},
            {"source": source, "value": "<p>Permitted scientific evidence.</p>"},
        ]
    )
    assert paper["abstract"] == "Permitted scientific evidence."
    assert paper["abstract_source"] == source
    assert paper["abstract_status"] == "available"
    assert "Restricted publisher" not in str(paper)
    assert "Unknown origin" not in str(paper)


@pytest.mark.parametrize("source", [None, "", "Publisher", "arxiv", "CERN/publisher", ["arXiv"]])
def test_unsupported_abstract_is_empty_with_explicit_provenance_status(source):
    paper = retrieve([{"source": source, "value": "Do not forward to the LLM"}])
    assert paper["abstract"] == ""
    assert paper["abstract_source"] == ""
    assert paper["abstract_status"] == "unavailable_source_not_permitted"
    assert "Do not forward" not in str(paper)


def test_missing_abstract_is_not_invented():
    paper = retrieve([])
    assert paper["abstract"] == ""
    assert paper["abstract_status"] == "unavailable"


def test_unavailable_abstract_cannot_reach_model_request(monkeypatch, settings):
    from research import ai

    settings.RESEARCH_SEARCH_BACKEND = "local"
    paper = retrieve([{"source": "Publisher", "value": "Restricted publisher evidence"}])

    def forbidden_request(*args, **kwargs):
        pytest.fail("A model request was made for an unsupported-source abstract")

    monkeypatch.setattr(ai, "_request", forbidden_request)
    with pytest.raises(ai.AIError, match="No readable abstracts"):
        ai.synthesize("Summarize the evidence", [paper])


def test_mixed_sources_only_forward_permitted_text_to_model(monkeypatch, settings):
    from research import ai

    settings.RESEARCH_SEARCH_BACKEND = "local"
    paper = retrieve(
        [
            {"source": "Publisher", "value": "Restricted publisher evidence"},
            {"source": "arXiv", "value": "Permitted scientific evidence"},
        ]
    )

    def inspect_request(prompt, schema):
        assert "Permitted scientific evidence" in prompt
        assert "Restricted publisher evidence" not in prompt
        raise RuntimeError("model boundary inspected")

    monkeypatch.setattr(ai, "_request", inspect_request)
    with pytest.raises(RuntimeError, match="model boundary inspected"):
        ai.synthesize("Summarize the evidence", [paper])


def retrieve(abstracts):
    data = {
        "hits": {
            "hits": [
                {
                    "id": "123",
                    "metadata": {
                        "titles": [{"title": "Scientific paper"}],
                        "abstracts": abstracts,
                    },
                }
            ]
        }
    }
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=data))
    ) as client:
        return search("science", client=client)[0]
