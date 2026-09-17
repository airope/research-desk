"""Owner-isolated bounded catalogue workflow; never writes public demo models."""

import csv
import hashlib
import io
import json

from django.db import transaction
from django.http import Http404
from django.utils import timezone

from records.matching import compare_metadata
from records.normalization import normalize_doi, normalize_record, normalize_title
from records.services import DomainError

from .models import AuditEvent, Catalogue, Entry, Selection

MAX_ENTRIES = 1000
MAX_SELECTION = 100
MAX_BASELINE = 500
EDITABLE_FIELDS = {"title", "doi", "year", "type", "authors", "journal"}


def _catalogue(owner, pk, lock=False):
    query = Catalogue.objects.select_for_update() if lock else Catalogue.objects
    if not owner.is_authenticated:
        raise Http404
    try:
        return query.get(pk=pk, owner=owner)
    except Catalogue.DoesNotExist as exc:
        raise Http404 from exc


def _revision(catalogue, expected):
    if catalogue.revision != expected:
        raise DomainError("stale_revision", "Catalogue changed. Reload before saving.")


def _bump(catalogue):
    catalogue.revision += 1
    catalogue.save(update_fields=["revision", "updated_at"])


def effective(entry):
    return {**entry.normalized, **{key: detail["value"] for key, detail in entry.overrides.items()}}


def _snapshot(entry):
    return {
        "status": entry.status,
        "merge_target": str(entry.merge_target_id) if entry.merge_target_id else None,
        "overrides": entry.overrides,
    }


def create_catalogue(owner, name):
    if not owner.is_authenticated:
        raise Http404
    name = str(name).strip()
    if not name or len(name) > 200:
        raise DomainError("invalid_name", "Provide a name of 1–200 characters.", 400)
    return Catalogue.objects.create(owner=owner, name=name)


def _validate_row(row):
    if (
        not isinstance(row, dict)
        or not isinstance(row.get("raw"), dict)
        or not isinstance(row.get("normalized"), dict)
    ):
        raise DomainError("invalid_row", "Rows require raw and normalized objects.", 400)
    if len(str(row.get("provider", row.get("source", "upload")))) > 32 or any(
        len(str(row.get(key, ""))) > 512 for key in ("external_id", "local_id")
    ):
        raise DomainError("invalid_row", "Source identifiers exceed the supported length.", 400)
    normalized = row["normalized"]
    # Validate adapter output through the same local metadata schema.
    try:
        normalize_record("upload", normalized)
    except (ValueError, TypeError) as exc:
        raise DomainError("invalid_row", str(exc), 400) from exc
    if not normalized.get("title") and not normalized.get("doi"):
        raise DomainError("invalid_row", "A title or DOI is required.", 400)


@transaction.atomic
def create_selection(owner, catalogue_id, kind, rows, errors=None, provenance=None):
    catalogue = _catalogue(owner, catalogue_id, lock=True)
    if kind not in ("baseline", "incoming"):
        raise DomainError("invalid_kind", "Choose baseline or incoming.", 400)
    limit = MAX_BASELINE if kind == "baseline" else MAX_SELECTION
    if not isinstance(rows, list) or len(rows) > limit:
        raise DomainError("selection_limit", f"Preview up to {limit} rows at a time.", 400)
    for row in rows:
        _validate_row(row)
    return Selection.objects.create(
        catalogue=catalogue, kind=kind, rows=rows, errors=errors or [], provenance=provenance or {}
    )


@transaction.atomic
def confirm_selection(owner, selection_id, expected_revision):
    if not owner.is_authenticated:
        raise Http404
    selection = (
        Selection.objects.select_related("catalogue")
        .filter(pk=selection_id, catalogue__owner=owner)
        .first()
    )
    if selection is None:
        raise Http404
    catalogue = _catalogue(owner, selection.catalogue_id, lock=True)
    selection.refresh_from_db()
    if selection.consumed:
        return selection
    _revision(catalogue, expected_revision)
    existing_count = catalogue.entries.count()
    created = skipped = changed = 0
    for position, row in enumerate(selection.rows):
        _validate_row(row)
        provider = row.get("provider", row.get("source", "upload"))
        external_id = row.get("external_id", "")
        existing = (
            catalogue.entries.filter(provider=provider, external_id=external_id).first()
            if external_id
            else None
        )
        if existing:
            skipped += 1
            changed += int(existing.normalized != row["normalized"] or existing.raw != row["raw"])
            continue
        created += 1
        if existing_count + created > MAX_ENTRIES:
            raise DomainError(
                "catalogue_limit", f"A catalogue supports at most {MAX_ENTRIES} rows.", 400
            )
        Entry.objects.create(
            catalogue=catalogue,
            selection=selection,
            position=position,
            origin=selection.kind,
            provider=row.get("provider", row.get("source", "upload")),
            external_id=row.get("external_id", ""),
            local_id=row.get("local_id", ""),
            raw=row["raw"],
            normalized=row["normalized"],
            status="kept" if selection.kind == "baseline" else "pending",
        )
    selection.summary = {
        "created": created,
        "skipped": skipped,
        "changed_existing": changed,
        "policy": "Existing source snapshots retained; changed remote content not applied.",
    }
    selection.consumed = True
    selection.confirmed_at = timezone.now()
    selection.save(update_fields=["consumed", "confirmed_at", "summary"])
    AuditEvent.objects.create(
        catalogue=catalogue,
        actor=owner,
        action="import",
        after={
            "selection_id": str(selection.pk),
            "kind": selection.kind,
            "rows": len(selection.rows),
            "summary": selection.summary,
            "provenance": selection.provenance,
        },
    )
    _bump(catalogue)
    return selection


def _entry(owner, pk):
    if not owner.is_authenticated:
        raise Http404
    entry = Entry.objects.filter(pk=pk, catalogue__owner=owner).first()
    if entry is None:
        raise Http404
    return entry


def group_comparison(entry, target):
    """Rank the projected root, but expose conflicts with every retained source."""
    incoming = effective(entry)
    selected, _ = projection(target)
    selected["title_key"] = normalize_title(selected.get("title", ""))
    comparison = compare_metadata(incoming, selected)
    evidence = []
    warnings = set(comparison["warnings"])
    members = [
        target,
        *target.merged_entries.exclude(pk=entry.pk).order_by("created_at", "position", "id"),
    ]
    for member in members:
        member_result = compare_metadata(incoming, effective(member))
        warnings.update(member_result["warnings"])
        evidence.append(
            {
                "entry_id": str(member.pk),
                "signals": member_result["signals"],
                "warnings": member_result["warnings"],
            }
        )
    comparison["warnings"] = sorted(warnings)
    comparison["group_evidence"] = evidence
    return comparison


def candidates(owner, entry_id, k=10):
    entry = _entry(owner, entry_id)
    results = []
    for other in entry.catalogue.entries.filter(status="kept").exclude(pk=entry.pk):
        comparison = group_comparison(entry, other)
        if (
            comparison["signals"]["doi"] == "identical"
            or (comparison["signals"]["title_similarity"] or 0) >= 0.3
        ):
            results.append({"entry": other, "comparison": comparison})
    results.sort(
        key=lambda item: (
            -item["comparison"]["ranking_score"],
            item["entry"].provider,
            item["entry"].external_id,
            str(item["entry"].pk),
        )
    )
    exact = [item for item in results if item["comparison"]["signals"]["doi"] == "identical"]
    lexical = [item for item in results if item["comparison"]["signals"]["doi"] != "identical"][
        : max(1, min(k, 100))
    ]
    return exact + lexical


def _deduplicate(catalogue, key, payload):
    if not key:
        return None, ""
    if len(key) > 128:
        raise DomainError("invalid_key", "Idempotency key is too long.", 400)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    prior = catalogue.events.filter(idempotency_key=key).first()
    if prior and prior.request_hash != digest:
        raise DomainError("idempotency_conflict", "This key was used for another action.")
    return prior, digest


@transaction.atomic
def decide(
    owner, entry_id, action, expected_revision, target_id=None, reason="", idempotency_key=""
):
    entry = _entry(owner, entry_id)
    catalogue = _catalogue(owner, entry.catalogue_id, lock=True)
    entry.refresh_from_db()
    payload = {
        "entry": str(entry_id),
        "action": action,
        "target": str(target_id) if target_id else None,
        "reason": reason,
        "revision": expected_revision,
    }
    prior, digest = _deduplicate(catalogue, idempotency_key, payload)
    if prior:
        return entry
    _revision(catalogue, expected_revision)
    if action not in ("keep", "merge", "exclude", "defer", "reset"):
        raise DomainError("invalid_action", "Unknown catalogue action.", 400)
    if entry.merged_entries.exists() and action != "keep":
        raise DomainError("dependent_merges", "Reset the entries merged into this record first.")
    before = _snapshot(entry)
    target = None
    if action == "merge":
        target = (
            catalogue.entries.filter(pk=target_id, status="kept", merge_target__isnull=True)
            .exclude(pk=entry.pk)
            .first()
        )
        if target is None:
            raise DomainError(
                "invalid_target", "Choose an included root record from this catalogue.", 400
            )
        comparison = group_comparison(entry, target)
        if comparison["warnings"] and not reason.strip():
            raise DomainError(
                "reason_required", "Conflicting evidence requires a merge reason.", 400
            )
    entry.status = {
        "keep": "kept",
        "merge": "merged",
        "exclude": "excluded",
        "defer": "deferred",
        "reset": "kept" if entry.origin == "baseline" else "pending",
    }[action]
    entry.merge_target = target
    entry.save(update_fields=["status", "merge_target"])
    AuditEvent.objects.create(
        catalogue=catalogue,
        entry=entry,
        actor=owner,
        action=action,
        reason=reason,
        before=before,
        after=_snapshot(entry),
        idempotency_key=idempotency_key or None,
        request_hash=digest,
    )
    _bump(catalogue)
    return entry


@transaction.atomic
def edit_fields(owner, entry_id, values, reason, expected_revision, idempotency_key=""):
    entry = _entry(owner, entry_id)
    catalogue = _catalogue(owner, entry.catalogue_id, lock=True)
    entry.refresh_from_db()
    prior, digest = _deduplicate(
        catalogue,
        idempotency_key,
        {"entry": str(entry_id), "values": values, "reason": reason, "revision": expected_revision},
    )
    if prior:
        return entry
    _revision(catalogue, expected_revision)
    if (
        not reason.strip()
        or not isinstance(values, dict)
        or not values
        or not set(values) <= EDITABLE_FIELDS
    ):
        raise DomainError(
            "invalid_correction", "Choose supported fields and provide a correction reason.", 400
        )
    try:
        checked = normalize_record("upload", {**effective(entry), **values})
    except (ValueError, TypeError) as exc:
        raise DomainError("invalid_correction", str(exc), 400) from exc
    if "journal" in values:
        if not isinstance(values["journal"], str):
            raise DomainError("invalid_correction", "Journal must be text.", 400)
        checked["journal"] = values["journal"]
    if "doi" in values and values["doi"] and not normalize_doi(values["doi"]):
        raise DomainError("invalid_doi", "Provide a valid DOI or leave it empty.", 400)
    before = _snapshot(entry)
    now = timezone.now().isoformat()
    overrides = dict(entry.overrides)
    for field in values:
        overrides[field] = {
            "value": checked[field],
            "actor_id": str(owner.pk),
            "reason": reason,
            "at": now,
        }
    if "title" in values:
        overrides["title_key"] = {
            "value": normalize_title(checked["title"]),
            "actor_id": str(owner.pk),
            "reason": reason,
            "at": now,
        }
    entry.overrides = overrides
    entry.save(update_fields=["overrides"])
    AuditEvent.objects.create(
        catalogue=catalogue,
        entry=entry,
        actor=owner,
        action="correct",
        reason=reason,
        before=before,
        after=_snapshot(entry),
        idempotency_key=idempotency_key or None,
        request_hash=digest,
    )
    _bump(catalogue)
    return entry


def _safe(value):
    text = (
        json.dumps(value, ensure_ascii=False)
        if isinstance(value, (dict, list))
        else str(value if value is not None else "")
    )
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else text


def projection(entry):
    """Root values take priority; merged sources only fill missing fields."""
    fields = ["title", "doi", "year", "type", "authors", "journal"]
    selected, provenance = {}, {}
    sources = [entry, *entry.merged_entries.order_by("created_at", "position", "id")]
    for source in sources:
        values = effective(source)
        for field in fields:
            if field not in selected and (values.get(field) or field in source.overrides):
                selected[field] = values[field]
                provenance[field] = {
                    "entry_id": str(source.pk),
                    "provider": source.provider,
                    "external_id": source.external_id,
                    "path": "overrides." + field
                    if field in source.overrides
                    else "normalized." + field,
                    "correction": source.overrides.get(field),
                    "policy": "root-first-fill-missing-v1",
                }
    return selected, provenance


@transaction.atomic
def export_csv(owner, catalogue_id, include_unresolved=False):
    catalogue = _catalogue(owner, catalogue_id, lock=True)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "entry_id",
            "local_id",
            "status",
            "included",
            "unresolved",
            "merge_target_id",
            "title",
            "doi",
            "year",
            "type",
            "authors",
            "journal",
            "provider",
            "external_id",
            "field_provenance",
            "source_entry_ids",
            "source_records",
            "catalogue_revision",
            "exported_at",
        ]
    )
    exported_at = timezone.now().isoformat()
    statuses = ["kept", "pending", "deferred"] if include_unresolved else ["kept"]
    for entry in catalogue.entries.filter(status__in=statuses):
        value, provenance = projection(entry)
        writer.writerow(
            [
                _safe(item)
                for item in [
                    entry.pk,
                    entry.local_id,
                    entry.status,
                    entry.status == "kept",
                    entry.status in ("pending", "deferred"),
                    entry.merge_target_id,
                    value.get("title"),
                    value.get("doi"),
                    value.get("year"),
                    value.get("type"),
                    value.get("authors"),
                    value.get("journal"),
                    entry.provider,
                    entry.external_id,
                    provenance,
                    [
                        str(entry.pk),
                        *[str(pk) for pk in entry.merged_entries.values_list("pk", flat=True)],
                    ],
                    [
                        {
                            "entry_id": str(source.pk),
                            "local_id": source.local_id,
                            "provider": source.provider,
                            "external_id": source.external_id,
                        }
                        for source in [
                            entry,
                            *entry.merged_entries.order_by("created_at", "position", "id"),
                        ]
                    ],
                    catalogue.revision,
                    exported_at,
                ]
            ]
        )
    return output.getvalue()


def export_changes(owner, catalogue_id):
    catalogue = _catalogue(owner, catalogue_id)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "event_id",
            "entry_id",
            "local_id",
            "provider",
            "external_id",
            "action",
            "actor_id",
            "timestamp",
            "reason",
            "before",
            "after",
        ]
    )
    for event in catalogue.events.select_related("entry").order_by("created_at", "id"):
        writer.writerow(
            [
                _safe(item)
                for item in [
                    event.pk,
                    event.entry_id,
                    event.entry.local_id if event.entry else None,
                    event.entry.provider if event.entry else None,
                    event.entry.external_id if event.entry else None,
                    event.action,
                    event.actor_id,
                    event.created_at.isoformat(),
                    event.reason,
                    event.before,
                    event.after,
                ]
            ]
        )
    return output.getvalue()


def demo_rows(incoming=False):
    # Import locally to keep acquisition independent of persistence.
    from django.conf import settings

    from .acquisition import demo_incoming, parse_csv

    if incoming:
        return demo_incoming()["rows"]
    return parse_csv((settings.BASE_DIR / "data/examples/catalogue.csv").read_bytes())["rows"]


@transaction.atomic
def create_demo(owner, name="Demo catalogue"):
    catalogue = create_catalogue(owner, name)
    selection = create_selection(
        owner,
        catalogue.pk,
        "baseline",
        demo_rows(),
        provenance={
            "origin": "simulated",
            "description": "Invented demonstration records; not real publications.",
        },
    )
    confirm_selection(owner, selection.pk, catalogue.revision)
    catalogue.refresh_from_db()
    return catalogue
