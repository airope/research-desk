"""Owner-scoped dossier search using the same retrieval path as report generation."""

from .retrieval import select_evidence


def search(dossier, query):
    papers = [
        {**paper, "_search_scope": f"{dossier.owner_id}:{dossier.pk}"}
        for paper in dossier.papers
        if paper["id"] in dossier.selected
    ]
    evidence = select_evidence(query, papers)
    results = [
        {**passage, "paper_id": paper["id"], "title": paper["title"]}
        for paper in evidence
        for passage in paper["_evidence_passages"]
        if passage["page"] > 0 and (passage.get("score") or 0) > 0
    ]
    results.sort(key=lambda p: -(p.get("score") or 0))
    return {"results": results, **(evidence[0]["_retrieval"] if evidence else {})}
