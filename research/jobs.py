"""Bounded jobs with persisted phases and cancellation fencing; no model code execution."""

import copy
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Dossier, ResearchRun
from .runs import finish, timed


class Cancelled(Exception):
    pass


def event(message):
    return {"message": message, "at": timezone.now().isoformat()}


def save_progress(pk, run_id, message, **changes):
    with transaction.atomic():
        dossier = (
            Dossier.objects.select_for_update()
            .only("run_id", "status", "events")
            .filter(pk=pk)
            .first()
        )
        if dossier is None or dossier.run_id != run_id or dossier.status != "running":
            raise Cancelled()
        for key, value in changes.items():
            setattr(dossier, key, value)
        dossier.events = [*dossier.events, event(message)][-100:]
        dossier.save(update_fields=[*changes, "events", "updated_at"])


def claim():
    with transaction.atomic():
        # A killed worker must not leave a dossier stuck indefinitely. No implicit LLM retry.
        expired = list(
            Dossier.objects.select_for_update()
            .only("id", "run_id", "status")
            .filter(status="running", updated_at__lt=timezone.now() - timedelta(minutes=10))
        )
        for stale in expired:
            finish(stale.run_id, "failed", "Worker stopped responding.")
            stale.status = "failed"
            stale.error = (
                "The worker stopped responding. Saved results are retained; retry to continue."
            )
            stale.run_id = uuid.uuid4()
            stale.save(update_fields=["status", "error", "run_id", "updated_at"])
        dossier = (
            Dossier.objects.select_for_update(skip_locked=True)
            .filter(status="queued")
            .order_by("created_at")
            .first()
        )
        if not dossier:
            return None
        dossier.status = "running"
        dossier.save(update_fields=["status", "updated_at"])
        ResearchRun.objects.get_or_create(
            id=dossier.run_id,
            defaults={"dossier": dossier, "stage": dossier.stage, "focus": dossier.focus},
        )
        return dossier


def execute(dossier):
    from . import ai, inspire

    pk, run_id = dossier.pk, dossier.run_id
    previous_papers = copy.deepcopy(dossier.report_papers or dossier.papers)
    try:
        if dossier.stage == "plan":
            if not ai.user_allowed(dossier.owner):
                raise ai.AIError("Local AI is reserved for the configured workstation owner.")
            save_progress(pk, run_id, "Preparing a search plan with the configured model.")
            plan = timed(
                run_id,
                "AI search plan",
                ai.generate_plan,
                dossier.question,
                dossier.year_from,
                dossier.limit,
            )
            save_progress(
                pk, run_id, "Search plan ready for you to edit.", plan=plan, status="draft"
            )
            return
        if dossier.stage == "investigate":
            if not ai.user_allowed(dossier.owner):
                raise ai.AIError("Local AI is reserved for the configured workstation owner.")
            from .investigation import run

            report, papers, selected = run(dossier)
            publish_report(dossier, report, papers, selected, previous_papers)
            return
        papers = list(dossier.papers)
        if dossier.stage == "search":
            papers, seen = [], set()
            queries = dossier.plan.get("queries", [])[:3]
            for index, query in enumerate(queries):
                save_progress(pk, run_id, f"Search {index + 1}/{len(queries)}: {query}")
                found = timed(
                    run_id,
                    "INSPIRE search",
                    inspire.search,
                    f"({query}) and date > {dossier.year_from - 1}",
                    limit=min(8, max(2, (dossier.limit + len(queries) - 1) // len(queries))),
                )
                for paper in found:
                    identity = paper["id"]
                    if identity not in seen and len(papers) < dossier.limit:
                        seen.add(identity)
                        papers.append(paper)
                save_progress(
                    pk,
                    run_id,
                    f"{len(papers)} unique papers retained so far.",
                    papers=papers,
                    selected=[p["id"] for p in papers],
                )
                if len(papers) >= dossier.limit:
                    break
            if not papers:
                save_progress(
                    pk,
                    run_id,
                    "No papers matched. Edit your search queries and try again.",
                    status="draft",
                )
                return
        dossier.refresh_from_db()
        if dossier.use_fulltext:
            from .fulltext import fetch_document

            attempted = 0
            for paper in sorted(papers, key=lambda p: bool(p.get("document"))):
                if (
                    paper["id"] not in dossier.selected
                    or paper.get("document", {}).get("status") == "available"
                ):
                    continue
                if attempted >= 6:
                    break
                save_progress(
                    pk, run_id, "Reading available PDF: " + paper["title"][:100], stage="fulltext"
                )
                paper["document"] = timed(run_id, "PDF extraction", fetch_document, paper)
                attempted += 1
                save_progress(
                    pk,
                    run_id,
                    "PDF " + paper["document"]["status"] + ": " + paper["title"][:100],
                    papers=papers,
                )
        dossier.refresh_from_db()
        chosen = [
            p
            for p in papers
            if p["id"] in dossier.selected
            and (
                p.get("abstract")
                or (
                    p.get("document", {}).get("status") == "available"
                    and any(page.get("text") for page in p.get("document", {}).get("pages", []))
                )
            )
        ]
        if not chosen:
            save_progress(
                pk,
                run_id,
                "No selected source text available for synthesis.",
                status="ready",
                error="Select at least one paper with an abstract or extracted PDF text to generate a report.",
            )
            return
        save_progress(
            pk,
            run_id,
            f"Comparing evidence from {len(chosen)} publications and checking quoted passages.",
            stage="synthesize",
        )
        if not ai.user_allowed(dossier.owner):
            raise ai.AIError("Local AI is reserved for the configured workstation owner.")
        index_current_sources(dossier, papers)
        chosen = [
            {
                **paper,
                "_search_scope": f"{dossier.owner_id}:{dossier.pk}",
                "_search_query": dossier.focus or dossier.question,
            }
            for paper in chosen
        ]
        report = timed(
            run_id,
            "AI synthesis",
            ai.synthesize,
            dossier.question
            + "\nScope: "
            + dossier.plan.get("scope", "")
            + "\nFocus for this report: "
            + dossier.focus,
            chosen,
        )
        publish_report(dossier, report, papers, dossier.selected, previous_papers)
    except Cancelled:
        return
    except Exception as exc:
        # Do not persist CLI stderr, credentials, or arbitrary HTTP bodies.
        from .ai import AIError
        from .search_index import SearchUnavailable

        message = (
            str(exc)
            if isinstance(exc, (AIError, inspire.SearchError, SearchUnavailable))
            else "Research could not finish. Saved results are retained. Retry or adjust the search."
        )
        try:
            save_progress(
                pk, run_id, "Research paused after an error.", status="failed", error=message[:500]
            )
        except Cancelled:
            pass

    finally:
        current = Dossier.objects.only("status", "run_id", "error").filter(pk=pk).first()
        finish(
            run_id,
            current.status if current and current.run_id == run_id else "cancelled",
            current.error if current and current.run_id == run_id else "",
        )


def publish_report(dossier, report, papers, selected, previous_papers):
    versions = dossier.versions
    if dossier.report:
        versions = [
            *versions,
            {
                "report": dossier.report,
                "focus": dossier.report_focus,
                "papers": previous_papers,
                "selected": dossier.report_selected,
                "at": timezone.now().isoformat(),
            },
        ][-10:]
    save_progress(
        dossier.pk,
        dossier.run_id,
        "Report ready. Check the cited passages before using its conclusions.",
        report=report,
        report_selected=selected,
        report_papers=copy.deepcopy(papers),
        report_focus=dossier.focus,
        versions=versions,
        status="ready",
        error="",
    )


def index_current_sources(dossier, papers):
    """Publish an index only while this job owns the dossier's current execution."""
    if settings.RESEARCH_SEARCH_BACKEND != "elasticsearch":
        return
    from .indexing import index_sources

    with transaction.atomic():
        current = (
            Dossier.objects.select_for_update()
            .only("run_id", "status")
            .filter(pk=dossier.pk)
            .first()
        )
        if current is None or current.run_id != dossier.run_id or current.status != "running":
            raise Cancelled()
        index_sources(papers, f"{dossier.owner_id}:{dossier.pk}")
