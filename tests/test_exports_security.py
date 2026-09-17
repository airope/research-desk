from types import SimpleNamespace

import pytest

from research.exports import markdown

ATTACK = '<img src="https://tracker.invalid/x"> ![pixel](https://tracker.invalid/y)\n# forged'
ESCAPED = '&lt;img src="https://tracker.invalid/x"&gt; \\!\\[pixel\\]\\(https://tracker.invalid/y\\) \\# forged'


def dossier():
    return SimpleNamespace(
        question="Question",
        year_from=2020,
        limit=8,
        report_stale=False,
        report_focus="Focus",
        plan={"queries": ["Query"]},
        selected=["123"],
        report_selected=["123"],
        papers=[],
        report_papers=[
            {
                "id": "123",
                "title": "Paper",
                "year": 2024,
                "source_url": "https://inspirehep.net/literature/123",
            }
        ],
        report={
            "llm": {"provider": "Provider", "model": "Model"},
            "summary": "Summary",
            "findings": [
                {
                    "heading": "Finding",
                    "text": "Text",
                    "evidence": [{"quote": "Quote", "paper_id": "123", "page": 2}],
                }
            ],
            "comparison": [
                {
                    "title": "Compared",
                    "paper_id": "123",
                    "method": "Method",
                    "result": "Result",
                    "limitations": "Limits",
                }
            ],
            "investigation": {
                "steps": [{"action": "Action", "reason": "Reason", "observation": "Observation"}],
                "stop_reason": "Stop",
            },
            "limitations": ["Limited"],
        },
    )


@pytest.mark.parametrize(
    "field",
    [
        "question",
        "year_from",
        "limit",
        "report_focus",
        "provider",
        "model",
        "summary",
        "heading",
        "text",
        "quote",
        "page",
        "comparison_title",
        "method",
        "result",
        "comparison_limits",
        "action",
        "reason",
        "observation",
        "stop_reason",
        "limitation",
        "query",
        "paper_title",
        "paper_year",
    ],
)
def test_every_dynamic_markdown_text_field_is_literal(field):
    d = dossier()
    if field in {"question", "year_from", "limit", "report_focus"}:
        setattr(d, field, ATTACK)
    elif field in {"provider", "model"}:
        d.report["llm"][field] = ATTACK
    elif field == "summary":
        d.report[field] = ATTACK
    elif field in {"heading", "text"}:
        d.report["findings"][0][field] = ATTACK
    elif field in {"quote", "page"}:
        d.report["findings"][0]["evidence"][0][field] = ATTACK
    elif field in {"comparison_title", "method", "result", "comparison_limits"}:
        key = {"comparison_title": "title", "comparison_limits": "limitations"}.get(field, field)
        d.report["comparison"][0][key] = ATTACK
    elif field in {"action", "reason", "observation"}:
        d.report["investigation"]["steps"][0][field] = ATTACK
    elif field == "stop_reason":
        d.report["investigation"][field] = ATTACK
    elif field == "limitation":
        d.report["limitations"] = [ATTACK]
    elif field == "query":
        d.plan["queries"] = [ATTACK]
    else:
        d.report_papers[0][{"paper_title": "title", "paper_year": "year"}[field]] = ATTACK
    exported = markdown(d)
    assert "<img" not in exported
    assert "![pixel]" not in exported
    assert "\n# forged" not in exported
    assert ESCAPED in exported


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html,<svg/onload=alert(1)>",
        "//tracker.invalid",
        "https://good.invalid/\n![pixel](https://tracker.invalid)",
        "https://name:secret@good.invalid/x",
        "https://good.invalid\\@evil.invalid/x",
        "https://[invalid",
        "https://good.invalid:bad/x",
    ],
)
def test_invalid_source_urls_are_not_exported_as_links(url):
    d = dossier()
    d.report_papers[0]["source_url"] = url
    exported = markdown(d)
    assert "Source URL unavailable" in exported
    assert url not in exported


def test_link_delimiters_are_percent_encoded():
    d = dossier()
    d.report_papers[0]["source_url"] = 'https://example.org/a(b)[c]<d>"e'
    exported = markdown(d)
    assert "(<https://example.org/a%28b%29%5Bc%5D%3Cd%3E%22e>)" in exported


def test_comparison_fallback_identifier_is_also_literal():
    d = dossier()
    del d.report["comparison"][0]["title"]
    d.report["comparison"][0]["paper_id"] = ATTACK
    assert ESCAPED in markdown(d)


def test_citation_identifier_cannot_escape_destination():
    d = dossier()
    d.report["findings"][0]["evidence"][0]["paper_id"] = ATTACK
    exported = markdown(d)
    assert "<img" not in exported
    assert "Citation unavailable" in exported


def test_readable_scientific_text_and_valid_citation_links_remain():
    d = dossier()
    d.report["summary"] = "α + β = 2; E < mc² & p > 0.05"
    exported = markdown(d)
    assert "α + β = 2; E &lt; mc² &amp; p &gt; 0.05" in exported
    assert (
        "[https://inspirehep.net/literature/123](<https://inspirehep.net/literature/123>)"
        in exported
    )
    assert "PDF page 2" in exported
