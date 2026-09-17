import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from records.services import DomainError

from .forms import CatalogueForm, EditForm, ExportForm, SelectionForm


def render_page(request, template, status=200, **context):
    return render(
        request, f"catalogues/{template}.html", {"active": "workspaces", **context}, status=status
    )


def owned_catalogue(request, pk):
    from .models import Catalogue

    return get_object_or_404(Catalogue, pk=pk, owner=request.user)


def rows_for_domain(rows):
    return [{**row, "provider": row.get("provider") or row.get("source") or "csv"} for row in rows]


def values(entry):
    from .services import effective

    return effective(entry)


@require_GET
def home(request):
    from .models import Catalogue

    catalogues = (
        Catalogue.objects.filter(owner=request.user)
        .annotate(entry_count=Count("entries"))
        .order_by("-updated_at")
        if request.user.is_authenticated
        else []
    )
    return render_page(request, "home", catalogues=catalogues)


@require_GET
def example(request):
    content = (settings.BASE_DIR / "data" / "examples" / "catalogue.csv").read_bytes()
    response = HttpResponse(content, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="catalogue-example.csv"'
    return response


@login_required
@require_http_methods(["GET", "POST"])
def new(request):
    from . import services
    from .acquisition import parse_csv

    form = CatalogueForm(request.POST or None, request.FILES or None, initial={"source": "csv"})
    if request.method == "POST" and form.is_valid():
        try:
            demo = form.cleaned_data["source"] == "demo"
            content = (
                (settings.BASE_DIR / "data" / "examples" / "catalogue.csv").read_bytes()
                if demo
                else form.cleaned_data["file"].read()
            )
            parsed = parse_csv(content)
            with transaction.atomic():
                catalogue = services.create_catalogue(request.user, form.cleaned_data["name"])
                draft = services.create_selection(
                    request.user,
                    catalogue.pk,
                    "baseline",
                    rows_for_domain(parsed["rows"]),
                    errors=parsed.get("errors", []),
                    provenance={
                        **parsed.get("provenance", {}),
                        "source": "demonstration" if demo else "uploaded_csv",
                        "filename": "catalogue-example.csv"
                        if demo
                        else form.cleaned_data["file"].name,
                        "total_known": parsed.get("total_known", True),
                        "total": parsed.get("total"),
                        "truncated": parsed.get("truncated", False),
                    },
                )
            return redirect("catalogues:preview", pk=draft.pk)
        except (ValueError, DomainError) as exc:
            form.add_error(None, str(exc))
    return render_page(request, "new", form=form)


@login_required
@require_GET
def detail(request, pk):
    catalogue = owned_catalogue(request, pk)
    status = request.GET.get("status", "")
    allowed = {"pending", "kept", "merged", "excluded", "deferred"}
    error = ""
    entries = catalogue.entries.all().order_by("-created_at")
    counts = dict(
        catalogue.entries.values("status")
        .annotate(count=Count("pk"))
        .values_list("status", "count")
    )
    if status:
        if status not in allowed:
            error = "Choose a valid result status."
            entries = entries.none()
        else:
            entries = entries.filter(status=status)
    query = request.GET.get("q", "").strip()[:200]
    if query:
        entries = entries.filter(
            Q(normalized__title__icontains=query)
            | Q(normalized__doi__icontains=query)
            | Q(local_id__icontains=query)
            | Q(overrides__title__value__icontains=query)
            | Q(overrides__doi__value__icontains=query)
        )
    page = Paginator(entries, 30).get_page(request.GET.get("page"))
    from . import services

    status_labels = {
        "pending": "To review",
        "kept": "Included",
        "merged": "Merged",
        "excluded": "Excluded",
        "deferred": "Needs investigation",
    }
    for item in page:
        item.display = services.projection(item)[0] if item.status == "kept" else values(item)
        item.status_label = status_labels[item.status]
        item.review_cue = "In your catalogue" if item.origin == "baseline" else "Processed"
        if item.status in {"pending", "deferred"}:
            matches = services.candidates(request.user, item.pk)
            strong = [
                match
                for match in matches
                if match["comparison"]["signals"].get("doi") == "identical"
                or (match["comparison"]["signals"].get("title_similarity") or 0) >= 0.85
            ]
            item.review_cue = (
                "Conflicting information"
                if any(match["comparison"]["warnings"] for match in strong)
                else "Possible duplicate"
                if strong
                else "New publication to check"
            )
    return render_page(
        request,
        "detail",
        catalogue=catalogue,
        page=page,
        counts=counts,
        total=catalogue.entries.count(),
        query=query,
        status_filter=status,
        error=error,
        selections=catalogue.selections.all().order_by("-created_at")[:5],
    )


@login_required
@require_http_methods(["GET", "POST"])
def selection(request, pk):
    from . import services
    from .acquisition import demo_incoming, search_inspire

    catalogue = owned_catalogue(request, pk)
    form = SelectionForm(
        request.POST or None, initial={"source": "demo", "type": "articles", "limit": 20}
    )
    if request.method == "POST" and form.is_valid():
        try:
            demo = form.cleaned_data["source"] == "demo"
            filters = {
                key: value
                for key, value in form.cleaned_data.items()
                if key != "source" and value not in (None, "")
            }
            result = demo_incoming() if demo else search_inspire(filters)
            provenance = {
                **result.get("provenance", {}),
                "source": "demonstration" if demo else "inspire",
                "query": result.get("query", ""),
                "filters": filters if not demo else {},
                "total": result.get("total"),
                "truncated": result.get("truncated", False),
            }
            draft = services.create_selection(
                request.user,
                catalogue.pk,
                "incoming",
                rows_for_domain(result["rows"]),
                errors=result.get("errors", []),
                provenance=provenance,
            )
            return redirect("catalogues:preview", pk=draft.pk)
        except (ValueError, DomainError) as exc:
            form.add_error(None, str(exc))
    return render_page(request, "selection", catalogue=catalogue, form=form)


@login_required
@require_http_methods(["GET", "POST"])
def preview(request, pk):
    from . import services
    from .models import Selection

    draft = get_object_or_404(
        Selection.objects.select_related("catalogue"), pk=pk, catalogue__owner=request.user
    )
    error = ""
    response_status = 200
    if request.method == "POST":
        try:
            if draft.errors and request.POST.get("acknowledge_errors") != "yes":
                raise ValueError(
                    "Confirm that you want to continue with valid rows; rejected rows remain in this import report."
                )
            revision = int(request.POST.get("expected_revision", ""))
            services.confirm_selection(request.user, draft.pk, revision)
            messages.success(
                request,
                "Selection added to this catalogue. Review the incoming records before exporting.",
            )
            return redirect("catalogues:detail", pk=draft.catalogue_id)
        except (ValueError, DomainError) as exc:
            error = str(exc)
            response_status = getattr(exc, "status", 400)
    return render_page(
        request,
        "preview",
        status=response_status,
        draft=draft,
        catalogue=draft.catalogue,
        error=error,
    )


@login_required
@require_http_methods(["GET", "POST"])
def entry(request, pk):
    from . import services
    from .models import Entry

    item = get_object_or_404(
        Entry.objects.select_related("catalogue", "merge_target"),
        pk=pk,
        catalogue__owner=request.user,
    )
    error, response_status = "", 200
    edit_baseline = services.projection(item)[0] if item.status == "kept" else values(item)
    edit = EditForm(
        initial={
            **edit_baseline,
            "expected_revision": item.catalogue.revision,
            "idempotency_key": str(uuid.uuid4()),
        }
    )
    if request.method == "POST":
        try:
            if request.POST.get("operation") == "edit":
                edit = EditForm(request.POST)
                if edit.is_valid():
                    data = edit.cleaned_data.copy()
                    reason, revision, key = (
                        data.pop("reason"),
                        data.pop("expected_revision"),
                        data.pop("idempotency_key"),
                    )
                    changed = {
                        field: value
                        for field, value in data.items()
                        if value != edit_baseline.get(field, None if field == "year" else "")
                    }
                    if not changed:
                        messages.info(request, "No fields changed.")
                        return redirect("catalogues:entry", pk=item.pk)
                    services.edit_fields(
                        request.user, item.pk, changed, reason, revision, idempotency_key=key
                    )
                else:
                    raise ValueError("Correct the highlighted fields.")
            else:
                services.decide(
                    request.user,
                    item.pk,
                    request.POST.get("action", ""),
                    int(request.POST.get("expected_revision", "")),
                    target_id=str(uuid.UUID(request.POST["target_id"]))
                    if request.POST.get("target_id")
                    else None,
                    reason=request.POST.get("reason", ""),
                    idempotency_key=request.POST.get("idempotency_key", ""),
                )
            messages.success(
                request, "Catalogue updated. Source metadata is preserved in the history."
            )
            return redirect("catalogues:entry", pk=item.pk)
        except (ValueError, DomainError) as exc:
            error, response_status = str(exc), getattr(exc, "status", 400)
    item.refresh_from_db()
    item.display, field_provenance = (
        services.projection(item) if item.status == "kept" else (values(item), {})
    )
    matches = services.candidates(request.user, item.pk)
    signal_labels = {
        "doi": "DOI",
        "title_similarity": "Title similarity",
        "author_similarity": "Author similarity",
        "type": "Document type",
        "year": "Publication year",
    }
    warning_labels = {
        "different_doi": "DOI values differ",
        "different_type": "Document types differ",
        "doi_title_conflict": "Matching DOI but conflicting titles",
        "negation_differs": "Titles differ in negation",
        "numbers_differ": "Numbers in titles differ",
        "dates_differ": "Publication years differ",
    }

    def present_signals(signals):
        return [
            {
                "label": signal_labels.get(name, name.replace("_", " ").capitalize()),
                "value": value,
                "numeric": isinstance(value, (int, float)) and not isinstance(value, bool),
            }
            for name, value in signals.items()
        ]

    for match in matches:
        match["entry"].display = services.projection(match["entry"])[0]
        match["signals"] = present_signals(match["comparison"]["signals"])
        match["warnings"] = [
            warning_labels.get(name, name.replace("_", " ").capitalize())
            for name in match["comparison"]["warnings"]
        ]
        for evidence in match["comparison"].get("group_evidence", []):
            evidence["display_signals"] = present_signals(evidence["signals"])
            evidence["display_warnings"] = [
                warning_labels.get(name, name.replace("_", " ").capitalize())
                for name in evidence["warnings"]
            ]
    next_entry = (
        item.catalogue.entries.filter(status__in=["pending", "deferred"])
        .exclude(pk=item.pk)
        .order_by("created_at")
        .first()
    )
    return render_page(
        request,
        "entry",
        status=response_status,
        catalogue=item.catalogue,
        entry=item,
        matches=matches,
        edit_form=edit,
        error=error,
        key=str(uuid.uuid4()),
        history=item.catalogue.events.filter(entry_id=item.pk).order_by("-created_at"),
        next_entry=next_entry,
        field_provenance=field_provenance,
    )


@login_required
@require_http_methods(["GET", "POST"])
def export(request, pk):
    from . import services

    catalogue = owned_catalogue(request, pk)
    form = ExportForm(
        request.POST or None, initial={"format": "catalogue", "unresolved": "exclude"}
    )
    if request.method == "POST" and form.is_valid():
        include_unresolved = form.cleaned_data["unresolved"] == "include"
        kind = form.cleaned_data["format"]
        content = (
            services.export_csv(request.user, catalogue.pk, include_unresolved=include_unresolved)
            if kind == "catalogue"
            else services.export_changes(request.user, catalogue.pk)
        )
        response = HttpResponse(content, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="srr-{catalogue.pk}-{kind}.csv"'
        response["X-Content-Type-Options"] = "nosniff"
        return response
    return render_page(
        request,
        "export",
        catalogue=catalogue,
        form=form,
        unresolved=catalogue.entries.filter(status__in=["pending", "deferred"]).count(),
    )
