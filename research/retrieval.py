"""Deterministic, bounded passage selection; no model or network calls."""

import re

from django.conf import settings

MAX_PAPERS = 20
MAX_CHARACTERS = 80_000
MAX_PAPER_CHARACTERS = 4_000
CHUNK_CHARACTERS = 1_200
STOP_WORDS = frozenset(
    "a an the and or in on at for of to with is are how what which compare approaches "
    "papers research studies their this that from between using about".split()
)


def _tokens(text):
    return set(re.findall(r"[\w-]{3,}", text.lower())) - STOP_WORDS


def _chunks(text):
    """Keep exact substrings and prefer whitespace boundaries."""
    start = 0
    while start < len(text):
        end = min(start + CHUNK_CHARACTERS, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + CHUNK_CHARACTERS // 2, end)
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            yield chunk
        start = end


def select_evidence(question, papers):
    """Return only text supplied to the model; page zero always means abstract."""
    engine, warning, ranked = "local-keywords", "", None
    if settings.RESEARCH_SEARCH_BACKEND == "elasticsearch":
        from .search_index import SearchUnavailable, ranked_passages

        scopes = {p.get("_search_scope", "") for p in papers}
        try:
            if len(scopes) != 1:
                raise SearchUnavailable("Elasticsearch needs one dossier scope.")
            ranked = ranked_passages(question, papers, next(iter(scopes)))
            engine = "elasticsearch-bm25"
        except SearchUnavailable as exc:
            warning = str(exc)
            engine, ranked = "unavailable", {}
    query = _tokens(question)
    selected = []
    remaining = MAX_CHARACTERS
    for paper in papers[:MAX_PAPERS]:
        budget = min(MAX_PAPER_CHARACTERS, remaining)
        passages = []
        abstract = (paper.get("abstract") or "")[: min(1_000, budget)]
        if abstract:
            passages.append({"page": 0, "text": abstract})
            budget -= len(abstract)
        candidates = []
        document = paper.get("document") or {}
        if document.get("status") == "available":
            for page in document.get("pages", []):
                number = page.get("page")
                if type(number) is not int or number < 1:
                    continue
                for index, chunk in enumerate(_chunks(page.get("text") or "")):
                    tokens = _tokens(chunk)
                    score = len(query & tokens)
                    candidates.append((score, number, index, chunk))
        candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
        if ranked is not None:
            candidates = ranked.get(paper["id"], [])
        for score, number, _, chunk in candidates[:5]:
            if budget < 80:
                break
            text = chunk[:budget]
            passages.append({"page": number, "text": text, "score": score})
            budget -= len(text)
        if passages or warning:
            selected.append(
                {
                    "id": paper["id"],
                    "title": paper["title"],
                    "year": paper.get("year"),
                    "source_url": paper.get("source_url"),
                    "_evidence_passages": passages,
                    "_retrieval": {"engine": engine, "warning": warning},
                }
            )
            remaining -= sum(len(item["text"]) for item in passages)
        if remaining <= 0:
            break
    return selected


def source_passages(paper):
    """Selected evidence is authoritative, even when the list is empty."""
    if "_evidence_passages" in paper:
        return paper["_evidence_passages"]
    passages = []
    if paper.get("abstract"):
        passages.append({"page": 0, "text": paper["abstract"]})
    document = paper.get("document") or {}
    if document.get("status") == "available":
        passages.extend(document.get("pages", []))
    return passages
