"""A maximum of three approved read-only actions, with cancellation checkpoints."""

import copy

from . import ai, inspire, investigator
from .fulltext import fetch_document
from .retrieval import select_evidence
from .runs import timed


def merge_evidence(previous, latest):
    merged = {p["id"]: copy.deepcopy(p) for p in previous}
    for paper in latest:
        old = merged.get(paper["id"], {}).get("_evidence_passages", [])
        passages, seen, budget = [], set(), 4000
        for passage in paper["_evidence_passages"] + old:
            key = (passage["page"], passage["text"])
            if key in seen or budget < 80:
                continue
            seen.add(key)
            text = passage["text"][:budget]
            passages.append({**passage, "text": text})
            budget -= len(text)
        merged[paper["id"]] = {**paper, "_evidence_passages": passages}
    return list(merged.values())[:20]


def run(dossier):
    from .jobs import index_current_sources, save_progress
    from .search_index import documents

    state = {"steps": [], "stop_reason": "", "max_actions": 3}
    papers = copy.deepcopy(dossier.papers)
    selected = list(dossier.selected)
    initial_ids = {p["id"] for p in papers}
    question = dossier.focus or dossier.question
    scope = f"{dossier.owner_id}:{dossier.pk}"

    def checkpoint(message):
        save_progress(
            dossier.pk,
            dossier.run_id,
            message,
            stage="investigate",
            papers=papers,
            selected=selected,
            investigation=state,
        )

    indexed_revision = None

    def retrieve(query):
        nonlocal indexed_revision
        revision, _ = documents(papers, scope)
        if revision != indexed_revision:
            index_current_sources(dossier, papers)
            indexed_revision = revision
        sources = [{**p, "_search_scope": scope} for p in papers if p["id"] in selected]
        return timed(
            dossier.run_id, "Investigation passage search", select_evidence, query, sources
        )

    checkpoint("Investigation started: at most 3 actions and 6 new papers.")
    evidence = retrieve(question)
    seen = set()
    for number in range(3):
        checkpoint(f"Choosing investigation action {number + 1}/3.")
        chosen = [p for p in papers if p["id"] in selected]
        decision = timed(
            dossier.run_id,
            "AI investigation decision",
            investigator.decide,
            question,
            chosen,
            evidence,
            state["steps"],
        )
        investigator.validate(decision, chosen)
        signature = tuple(
            decision[k] for k in ("action", "query", "paper_id", "reference_id", "page")
        )
        if signature in seen:
            state["stop_reason"] = "Stopped because the proposed action was repeated."
            break
        seen.add(signature)
        step = {**decision, "status": "running", "observation": ""}
        state["steps"].append(step)
        checkpoint(decision["action"] + ": " + decision["reason"])
        if decision["action"] == "finish":
            step.update(status="completed", observation="No further acquisition requested.")
            state["stop_reason"] = decision["reason"]
            break
        try:
            if decision["action"] == "read_page":
                target = next(p for p in papers if p["id"] == decision["paper_id"])
                page = next(p for p in target["document"]["pages"] if p["page"] == decision["page"])
                evidence = merge_evidence(
                    evidence,
                    [
                        {
                            "id": target["id"],
                            "title": target["title"],
                            "year": target.get("year"),
                            "source_url": target["source_url"],
                            "_evidence_passages": [
                                {"page": page["page"], "text": page["text"][:4000]}
                            ],
                            "_retrieval": {"engine": "direct-page", "warning": ""},
                        }
                    ],
                )
                step.update(
                    status="completed",
                    observation=f"Read PDF page {page['page']} of INSPIRE {target['id']} (up to 4000 characters).",
                )
                checkpoint(step["observation"])
                continue
            if decision["action"] == "read_pdf" and next(
                p for p in chosen if p["id"] == decision["paper_id"]
            ).get("document"):
                step.update(
                    status="skipped",
                    observation="PDF already attempted; use read_page to inspect an available page.",
                )
                checkpoint(step["observation"])
                continue
            fresh = perform(decision, papers, selected, initial_ids, dossier)
            step.update(status="completed", observation=fresh)
            checkpoint(step["observation"])
            query = decision["query"] if decision["action"] == "passages" else question
            latest = retrieve(query)
            step["sources"] = [
                {
                    "paper_id": p["id"],
                    "pages": sorted({v["page"] for v in p["_evidence_passages"]}),
                    "engine": p.get("_retrieval", {}).get("engine", ""),
                }
                for p in latest
            ]
            evidence = merge_evidence(evidence, latest)
        except inspire.SearchError as exc:
            step.update(status="failed", observation=str(exc))
        checkpoint(step["observation"])
    if not state["stop_reason"]:
        state["stop_reason"] = "The three-action budget was reached."
    checkpoint(state["stop_reason"])
    if not evidence:
        raise ai.AIError(
            "No source evidence was collected. Adjust the selection or research question."
        )
    report = timed(dossier.run_id, "AI investigation synthesis", ai.synthesize, question, evidence)
    report["investigation"] = copy.deepcopy(state)
    report["limitations"].append("Investigation stopped: " + state["stop_reason"])
    return report, papers, selected


def perform(decision, papers, selected, initial_ids, dossier):
    action = decision["action"]
    paper = next((p for p in papers if p["id"] == decision["paper_id"]), None)
    if action == "passages":
        return "Searched selected source passages for: " + decision["query"]
    if action == "read_pdf":
        if paper.get("document"):
            return "PDF already attempted; existing evidence retained."
        paper["document"] = timed(
            dossier.run_id, "Investigation PDF extraction", fetch_document, paper
        )
        doc = paper["document"]
        return f"PDF {doc['status']}: {len(doc['pages'])} pages. {doc['error']}"
    capacity = min(20 - len(papers), 6 - len({p["id"] for p in papers} - initial_ids))
    if capacity <= 0:
        return "Paper limit reached; no external search performed."
    query = decision["query"]
    if action == "reference":
        query = "recid:" + decision["reference_id"]
    elif action == "citations":
        query = "refersto:recid:" + decision["paper_id"]
    if action != "reference":
        query = f"({query}) and date > {dossier.year_from - 1}"
    found = timed(
        dossier.run_id,
        "Investigation INSPIRE search",
        inspire.search,
        query,
        limit=min(2, capacity),
    )
    known = {p["id"] for p in papers}
    added = []
    for result in found:
        if action == "reference" and result["id"] != decision["reference_id"]:
            continue
        if result["id"] in known:
            continue
        known.add(result["id"])
        result["acquisition"] = {"action": action, "query": query, "parent": decision["paper_id"]}
        papers.append(result)
        selected.append(result["id"])
        added.append(result["id"])
    return f"INSPIRE query: {query}. Added {len(added)} papers" + (
        ": " + ", ".join(added) if added else "."
    )
