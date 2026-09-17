"""Portable report exports, retaining source evidence and scope limitations."""

import re
from html import escape
from urllib.parse import quote, urlsplit


def bibliography(dossier):
    lines = []
    for paper in dossier.report_papers or dossier.papers:
        if paper["id"] not in (dossier.report_selected if dossier.report else dossier.selected):
            continue

        def escape(value):
            return re.sub(r"[{}\\\r\n]", " ", str(value or ""))

        lines.append(
            "@article{inspire"
            + paper["id"]
            + ",\n"
            + ",\n".join(
                f"  {key} = {{{escape(value)}}}"
                for key, value in {
                    "title": paper["title"],
                    "author": " and ".join(paper["authors"]),
                    "year": paper["year"],
                    "doi": paper["doi"],
                    "url": paper["source_url"],
                }.items()
                if value
            )
            + "\n}"
        )
    return "\n\n".join(lines)


def _literal(value):
    """Render metadata/model output as text, not HTML or Markdown structure.

    Collapse field-internal whitespace so fields cannot start new blocks or
    escape a quote/list. Escape before insertion, never after adding our markup.
    """
    text = " ".join(str(value if value is not None else "").split())
    text = escape(text, quote=False)
    text = re.sub(r"([\\`*_{}\[\]()#!|~])", r"\\\1", text)
    text = re.sub(r"^([+\-=])", r"\\\1", text)
    return re.sub(r"^(\d+)\.", r"\1\\.", text)


def _link(value):
    """Only absolute HTTP(S) destinations; delimiters cannot escape the link."""
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 for c in value):
        return "Source URL unavailable"
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or "\\" in value
            or parsed.port == 0
        ):
            return "Source URL unavailable"
    except ValueError:
        return "Source URL unavailable"
    destination = escape(quote(value, safe=":/?#@!$&*+,;=%~.-_"), quote=True)
    return f"[{_literal(value)}](<{destination}>)"


def _citation(identifier):
    if not re.fullmatch(r"\d{1,20}", str(identifier)):
        return "Citation unavailable"
    return _link(f"https://inspirehep.net/literature/{identifier}")


def markdown(dossier):
    report = dossier.report
    lines = [
        "# " + _literal(dossier.question),
        "",
        "AI draft based on retrieved abstract and PDF passages; not exhaustive full-paper analysis.",
        "Bounded INSPIRE search; not a systematic review. Verify conclusions against source evidence.",
        f"Since {_literal(dossier.year_from)}; maximum {_literal(dossier.limit)} papers.",
        "",
    ]
    if report.get("llm"):
        lines += [
            f"Model: {_literal(report['llm']['provider'])} / {_literal(report['llm']['model'])}",
            "",
        ]
    if dossier.report_stale:
        lines += [
            "Selection changed after this report was generated. This export retains the previous report and its sources.",
            "",
        ]
    if dossier.report_focus:
        lines += ["Report focus: " + _literal(dossier.report_focus), ""]
    lines += [_literal(report.get("summary", "No AI report generated.")), ""]
    for finding in report.get("findings", []):
        lines += ["## " + _literal(finding["heading"]), "", _literal(finding["text"]), ""]
        for evidence in finding["evidence"]:
            lines += [
                "> " + _literal(evidence["quote"]),
                f"Source: {_citation(evidence['paper_id'])} · "
                + (
                    f"PDF page {_literal(evidence['page'])}" if evidence.get("page") else "Abstract"
                ),
                "",
            ]
    lines += ["## Comparison", ""]
    for row in report.get("comparison", []):
        lines += [
            "### " + _literal(row.get("title", row["paper_id"])),
            "Method: " + _literal(row["method"]),
            "Result: " + _literal(row["result"]),
            "Limitations: " + _literal(row["limitations"]),
            "",
        ]
    if report.get("investigation"):
        lines += ["## Investigation", ""]
        for step in report["investigation"]["steps"]:
            lines += [
                f"- {_literal(step['action'])}: {_literal(step['reason'])} — {_literal(step['observation'])}"
            ]
        lines += [_literal(report["investigation"]["stop_reason"]), ""]
    lines += [
        "## Limitations",
        *["- " + _literal(s) for s in report.get("limitations", [])],
        "",
        "## Search queries",
        *["- " + _literal(q) for q in dossier.plan.get("queries", [])],
        "",
        "## Sources",
    ]
    for p in dossier.report_papers or dossier.papers:
        if p["id"] in (dossier.report_selected if dossier.report else dossier.selected):
            lines.append(
                f"- {_literal(p['title'])} ({_literal(p['year'] or 'n.d.')}). {_link(p['source_url'])}"
            )
    return "\n".join(lines) + "\n"
