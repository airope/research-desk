from collections import Counter

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from . import ai
from .forms import QuestionForm
from .jobs import event
from .models import Dossier
from .reviews import counts, fingerprint


def capability(user):
    if not ai.user_allowed(user):
        return (
            False,
            "Local AI is reserved for the configured workstation owner. Manual INSPIRE search remains available.",
        )
    return ai.availability()


@require_http_methods(["GET", "POST"])
def home(request):
    if not request.user.is_authenticated:
        if request.method == "POST":
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login("/")
        return render(
            request,
            "research/home.html",
            {
                "form": QuestionForm(),
                "dossiers": [],
                "ai_available": False,
                "ai_message": "Sign in to keep your research dossiers private.",
            },
        )
    available, message = capability(request.user)
    form = QuestionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        from .limits import LimitExceeded, admit_job, configured, consume

        try:
            with transaction.atomic():
                consume(
                    "dossiers-daily",
                    request.user.pk,
                    configured("RESEARCH_DAILY_DOSSIERS", 30),
                    86400,
                )
                if available:
                    admit_job(request.user.pk)
                dossier = Dossier.objects.create(
                    owner=request.user,
                    **form.cleaned_data,
                    status="queued" if available else "draft",
                    plan={}
                    if available
                    else {"scope": form.cleaned_data["question"], "queries": []},
                    events=[
                        event(
                            "Dossier created. Planning will use the configured model."
                            if available
                            else "Enter up to three INSPIRE queries to search without AI."
                        )
                    ],
                )
        except LimitExceeded as exc:
            response = HttpResponse(str(exc), status=429)
            response["Retry-After"] = str(exc.retry_after)
            return response
        return redirect("research:detail", pk=dossier.pk)
    return render(
        request,
        "research/home.html",
        {
            "form": form,
            "dossiers": Dossier.objects.filter(owner=request.user).only(
                "id", "question", "status", "created_at"
            )[:30],
            "ai_available": available,
            "ai_message": message,
        },
    )


@login_required
@require_safe
def detail(request, pk):
    dossier = get_object_or_404(Dossier, pk=pk, owner=request.user)
    tab = request.GET.get("tab", "papers")
    if tab not in {"papers", "compare", "report", "passages"}:
        tab = "papers"
    passage_query = request.GET.get("q", "").strip()[:500]
    passage_search = {}
    if tab == "passages" and passage_query:
        from .passage_search import search

        passage_search = search(dossier, passage_query)
    evidence_papers = (
        (dossier.report_papers or dossier.papers)
        if tab in {"report", "compare"}
        else dossier.papers
    )
    selected_paper = next((p for p in evidence_papers if p["id"] == request.GET.get("paper")), None)
    page_number = request.GET.get("page", "0")
    try:
        page_number = max(0, int(page_number))
    except ValueError:
        page_number = 0
    source_text = ""
    if selected_paper:
        from .evidence import passages

        source_text = (
            selected_paper.get("abstract", "")
            if page_number == 0
            else next(
                (
                    p["text"]
                    for p in selected_paper.get("document", {}).get("pages", [])
                    if p["page"] == page_number
                ),
                "",
            )
        )
        selected_paper["passages"] = passages(
            source_text,
            {
                "findings": [
                    {
                        "evidence": [
                            {"paper_id": p["paper_id"], "page": p["page"], "quote": p["text"]}
                            for p in passage_search.get("results", [])
                        ]
                    }
                ]
            }
            if tab == "passages"
            else dossier.report,
            selected_paper["id"],
            page_number,
        )
    available, message = capability(request.user)
    return render(
        request,
        "research/detail.html",
        {
            "dossier": dossier,
            "passage_query": passage_query,
            "passage_search": passage_search,
            "source_page": page_number,
            "source_text": source_text,
            "report_token": fingerprint(dossier.report),
            "review_counts": counts(dossier.report),
            "runs": dossier.runs.all()[:10],
            "fulltext_count": sum(
                p.get("document", {}).get("status") == "available" for p in dossier.papers
            ),
            "plan": dossier.plan,
            "papers": dossier.papers,
            "selected": dossier.selected,
            "selected_paper": selected_paper,
            "tab": tab,
            "report": dossier.report,
            "report_exists": bool(dossier.report),
            "report_stale": dossier.report_stale,
            "events": dossier.events,
            "error": dossier.error,
            "running": dossier.status in {"queued", "running"},
            "updated_at": dossier.updated_at.isoformat(),
            "paper_count": len(dossier.papers),
            "selection_count": len(dossier.selected),
            "ai_available": available,
            "ai_message": message,
            "last_event": dossier.events[-1] if dossier.events else {},
            "timeline": sorted(Counter(p["year"] for p in dossier.papers if p.get("year")).items()),
        },
    )


@login_required
@require_POST
def action(request, pk):
    from .commands import CommandError
    from .limits import LimitExceeded

    try:
        with transaction.atomic():
            dossier = get_object_or_404(
                Dossier.objects.select_for_update(), pk=pk, owner=request.user
            )
            from .commands import apply_command

            command = apply_command(dossier, request.user, request.POST, capability)

    except (CommandError, LimitExceeded) as exc:
        if isinstance(exc, LimitExceeded):
            response = HttpResponse(str(exc), status=429)
            response["Retry-After"] = str(exc.retry_after)
            return response
        if exc.bad_request:
            return HttpResponseBadRequest(str(exc))
        messages.error(request, str(exc))
        return redirect("research:detail", pk=pk)
    destination = reverse("research:detail", kwargs={"pk": pk})
    if command in {"review", "fulltext", "followup", "regenerate", "investigate"}:
        destination += "?tab=report"
    return redirect(destination)


@login_required
@require_safe
def export(request, pk):
    from .exports import bibliography, markdown

    dossier = get_object_or_404(Dossier, pk=pk, owner=request.user)
    kind = request.GET.get("format", "md")
    if kind == "html":
        return render(
            request,
            "research/print.html",
            {
                "dossier": dossier,
                "report": dossier.report,
                "papers": [
                    p
                    for p in (dossier.report_papers or dossier.papers)
                    if p["id"] in dossier.report_selected
                ],
            },
        )
    if kind not in {"md", "bib"}:
        return HttpResponseBadRequest("Unknown export format")
    content = bibliography(dossier) if kind == "bib" else markdown(dossier)
    response = HttpResponse(content, content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="research-{dossier.pk}.{kind}"'
    return response


@login_required
@require_safe
def status(request, pk):
    dossier = get_object_or_404(
        Dossier.objects.only("status", "updated_at"), pk=pk, owner=request.user
    )
    return JsonResponse({"status": dossier.status, "updated_at": dossier.updated_at.isoformat()})


@login_required
@require_safe
def version(request, pk, index):
    dossier = get_object_or_404(Dossier, pk=pk, owner=request.user)
    if index < 0 or index >= len(dossier.versions):
        from django.http import Http404

        raise Http404()
    snapshot = dossier.versions[index]
    return render(
        request,
        "research/version.html",
        {
            "dossier": dossier,
            "snapshot": snapshot,
            "report": snapshot["report"],
            "index": index + 1,
        },
    )
