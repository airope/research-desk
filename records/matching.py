"""Explainable lexical baseline. Scores rank review work; they are not probabilities."""

import re

from rapidfuzz.fuzz import ratio

CONFIG = {
    "version": "lexical-v1",
    "automatic_association": False,
    "title_compatible": 0.85,
    "title_conflict": 0.5,
}


def compare_metadata(left, right):
    warnings = []
    ld, rd = left.get("doi"), right.get("doi")
    doi = "missing" if not ld or not rd else ("identical" if ld == rd else "different")
    lt, rt = left.get("title_key", ""), right.get("title_key", "")
    title = ratio(lt, rt) / 100 if lt and rt else None
    kinds = [left.get("type"), right.get("type")]
    kind = "missing" if not all(kinds) else ("identical" if kinds[0] == kinds[1] else "different")
    if doi == "different":
        warnings.append("different_doi")
    if kind == "different":
        warnings.append("different_type")
    if doi == "identical" and title is not None and title < CONFIG["title_conflict"]:
        warnings.append("doi_title_conflict")
    negations = {"no", "not", "without", "non", "neither"}
    if (set(re.findall(r"\w+", lt)) & negations) != (set(re.findall(r"\w+", rt)) & negations):
        warnings.append("negation_differs")
    if set(re.findall(r"\d+", lt)) != set(re.findall(r"\d+", rt)):
        warnings.append("numbers_differ")
    la, ra = left.get("authors", []), right.get("authors", [])

    def names(authors):
        return " ".join(
            (a.get("name", "") if isinstance(a, dict) else str(a)).casefold() for a in authors
        )

    authors = ratio(names(la), names(ra)) / 100 if la and ra else None
    years = [left.get("year"), right.get("year")]
    year = "missing" if not all(years) else ("identical" if years[0] == years[1] else "different")
    if year == "different":
        warnings.append("dates_differ")
    recommendation = (
        "review" if doi == "identical" or title is not None else "insufficient_evidence"
    )
    return {
        "signals": {
            "doi": doi,
            "title_similarity": title,
            "author_similarity": authors,
            "type": kind,
            "year": year,
        },
        "warnings": warnings,
        "ranking_score": max(title or 0, 1 if doi == "identical" else 0),
        "recommendation": recommendation,
    }
