import json
import uuid

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods
from rest_framework.exceptions import ValidationError

from .api import can_write, filter_pairs, pair_queryset
from .models import CandidatePair, CanonicalPublication, ReviewDecision, SourceRecord
from .serializers import DecisionInput, WithdrawInput
from .services import DomainError, decide, withdraw, withdrawal_preview


def context(request, **kwargs):
    return {
        "can_curate": can_write(request.user),
        "can_operate": can_write(request.user, "operator"),
        **kwargs,
    }


@require_GET
def queue(request):
    pairs = pair_queryset()
    error = ""
    try:
        pairs = filter_pairs(pairs, request.GET)
    except ValidationError as exc:
        pairs = pairs.none()
        error = str(exc.detail)
    page = Paginator(pairs, 20).get_page(request.GET.get("page"))
    stats = {
        "sources": SourceRecord.objects.count(),
        "publications": CanonicalPublication.objects.filter(state="active").count(),
        "pending": CandidatePair.objects.filter(
            state__in=["pending", "review", "needs_reassessment", "insufficient_evidence"]
        ).count(),
        "decisions": ReviewDecision.objects.exclude(action="withdraw").count(),
    }
    return render(
        request,
        "records/queue.html",
        context(request, page=page, stats=stats, error=error, active="queue"),
    )


@require_http_methods(["GET", "POST"])
def compare(request, pk):
    pair = get_object_or_404(pair_queryset(), pk=pk)
    error = ""
    response_status = 200
    if request.method == "POST":
        if not can_write(request.user):
            return HttpResponseForbidden("Curator access is required.")
        data = DecisionInput(data=request.POST)
        if data.is_valid():
            try:
                decide(pk, actor=request.user.get_username(), **data.validated_data)
                messages.success(
                    request, "Decision recorded. Original source records are preserved."
                )
                return redirect("compare", pk=pk)
            except DomainError as exc:
                error, response_status = str(exc), exc.status
        else:
            error, response_status = str(data.errors), 400
    proposal = next(iter(pair.proposals.all()), None)
    return render(
        request,
        "records/compare.html",
        context(
            request,
            pair=pair,
            active_decision=pair.decisions.filter(
                action__in=["accept", "reject"], withdrawal__isnull=True
            ).first(),
            proposal=proposal,
            error=error,
            key=str(uuid.uuid4()),
            active="queue",
        ),
        status=response_status,
    )


@require_http_methods(["GET", "POST"])
def withdrawal(request, pk):
    decision = get_object_or_404(ReviewDecision.objects.select_related("pair"), pk=pk)
    error = ""
    response_status = 200
    if request.method == "POST":
        if not can_write(request.user):
            return HttpResponseForbidden("Curator access is required.")
        data = WithdrawInput(data=request.POST)
        if data.is_valid():
            try:
                withdraw(pk, actor=request.user.get_username(), **data.validated_data)
                messages.success(request, "Decision withdrawn with a compensating audit event.")
                return redirect("compare", pk=decision.pair_id)
            except DomainError as exc:
                error, response_status = str(exc), exc.status
        else:
            error, response_status = str(data.errors), 400
    try:
        preview = withdrawal_preview(pk)
    except DomainError as exc:
        preview, error, response_status = {}, str(exc), exc.status
    record_ids = [pk for group in preview.get("groups", []) for pk in group]
    records = {
        str(record.pk): record
        for record in SourceRecord.objects.filter(pk__in=record_ids).select_related(
            "current_version"
        )
    }
    preview_groups = [
        [records[pk] for pk in group if pk in records] for group in preview.get("groups", [])
    ]
    return render(
        request,
        "records/withdraw.html",
        context(
            request,
            decision=decision,
            preview=preview,
            preview_groups=preview_groups,
            error=error,
            key=str(uuid.uuid4()),
        ),
        status=response_status,
    )


@require_GET
def catalogue(request):
    publications = (
        CanonicalPublication.objects.filter(state="active")
        .prefetch_related("records")
        .order_by("-updated_at")
    )
    query = request.GET.get("q", "")[:200].strip()
    if query:
        publications = publications.filter(
            Q(records__title_key__icontains=query) | Q(records__doi__icontains=query)
        ).distinct()
    return render(
        request,
        "records/catalogue.html",
        context(
            request,
            page=Paginator(publications, 20).get_page(request.GET.get("page")),
            query=query,
            active="catalogue",
        ),
    )


@require_GET
def publication(request, pk):
    pub = get_object_or_404(
        CanonicalPublication.objects.prefetch_related("records__versions"), pk=pk
    )
    ids = pub.memberships.values_list("record_id", flat=True)
    history = ReviewDecision.objects.filter(
        Q(pair__left_id__in=ids) | Q(pair__right_id__in=ids)
    ).distinct()
    return render(
        request,
        "records/publication.html",
        context(request, publication=pub, history=history, active="catalogue"),
    )


@require_http_methods(["GET", "POST"])
def imports(request):
    from .ingestion import ImportConflict, create_import, retry_run
    from .models import ImportRun

    error = ""
    if request.method == "POST":
        if not can_write(request.user, "operator"):
            return HttpResponseForbidden("Operator access is required.")
        try:
            if request.POST.get("retry"):
                run = get_object_or_404(ImportRun, pk=request.POST["retry"])
                retry_run(run.id)
            else:
                provider = request.POST.get("provider")
                if provider not in ["crossref", "openalex"]:
                    raise ValueError("Choose an allowed provider.")
                key = request.POST.get("idempotency_key", "")
                if not key or len(key) > 128:
                    raise ValueError("An idempotency key is required.")
                create_import(
                    provider, {"fixture": "demo", "page_size": 20, "max_records": 100}, key
                )
            messages.success(request, "Import queued. The worker processes the durable queue.")
            return redirect("imports")
        except (ImportConflict, ValueError) as exc:
            error = str(exc)
    runs = ImportRun.objects.order_by("-created_at")
    return render(
        request,
        "records/imports.html",
        context(
            request,
            page=Paginator(runs, 20).get_page(request.GET.get("page")),
            error=error,
            key=str(uuid.uuid4()),
            active="imports",
        ),
    )


@require_GET
def evaluation(request):
    path = settings.BASE_DIR / "data" / "benchmark-report.json"
    report = None
    if path.exists():
        try:
            report = json.loads(path.read_text())
        except (ValueError, OSError):
            pass
    return render(
        request,
        "records/evaluation.html",
        context(
            request,
            report=report,
            report_json=json.dumps(report, indent=2, ensure_ascii=False) if report else "",
            active="evaluation",
        ),
    )


@require_GET
def live(request):
    return JsonResponse({"status": "alive"})


@require_GET
def ready(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return JsonResponse({"status": "ready", "database": "available"})
    except Exception:
        return JsonResponse({"status": "unavailable", "database": "unavailable"}, status=503)
