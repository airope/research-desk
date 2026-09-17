import csv
import io
import json

import pytest
from django.contrib.auth.models import User
from django.db import DatabaseError, transaction
from django.http import Http404

from catalogues.models import AuditEvent, Entry
from catalogues.services import (
    candidates,
    confirm_selection,
    create_catalogue,
    create_selection,
    decide,
    edit_fields,
    effective,
    export_changes,
    export_csv,
    projection,
)
from records.models import SourceRecord
from records.normalization import normalize_record
from records.services import DomainError

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return User.objects.create_user("owner")


def row(key, title="A study", doi="", **extra):
    raw = {"title": title, "doi": doi, "type": "article", **extra}
    return {
        "source": "csv",
        "external_id": key,
        "local_id": key,
        "raw": raw,
        "normalized": normalize_record("csv", raw),
    }


def add(owner, catalogue, rows, kind="incoming"):
    catalogue.refresh_from_db()
    selection = create_selection(owner, catalogue.pk, kind, rows)
    confirm_selection(owner, selection.pk, catalogue.revision)
    catalogue.refresh_from_db()
    return selection


def action(owner, entry, action, **kwargs):
    entry.catalogue.refresh_from_db()
    return decide(owner, entry.pk, action, entry.catalogue.revision, **kwargs)


def test_private_snapshots_never_enter_public_graph(owner):
    catalogue = create_catalogue(owner, "Private")
    selection = add(owner, catalogue, [row("one")])
    assert selection.entries.get().status == "pending"
    assert SourceRecord.objects.count() == 0
    other = User.objects.create_user("other")
    with pytest.raises(Http404):
        export_csv(other, catalogue.pk)
    with pytest.raises(Http404):
        candidates(other, selection.entries.get().pk)
    with pytest.raises(Http404):
        confirm_selection(other, selection.pk, catalogue.revision)


def test_confirmation_idempotent_and_repeat_snapshot_preserved(owner):
    catalogue = create_catalogue(owner, "Private")
    selected = add(owner, catalogue, [row("one")], "baseline")
    confirm_selection(owner, selected.pk, 1)
    add(owner, catalogue, [row("one")])
    changed = add(owner, catalogue, [row("one", title="Remote change")])
    changed.refresh_from_db()
    assert catalogue.entries.count() == 1
    assert catalogue.entries.get().normalized["title"] == "A study"
    assert changed.summary["skipped"] == changed.summary["changed_existing"] == 1


def test_decision_revision_idempotency_and_foreign_target(owner):
    catalogue = create_catalogue(owner, "Private")
    source = add(owner, catalogue, [row("one")]).entries.get()
    initial = catalogue.revision
    decide(owner, source.pk, "keep", initial, idempotency_key="save")
    decide(owner, source.pk, "keep", initial, idempotency_key="save")
    with pytest.raises(DomainError, match="changed"):
        decide(owner, source.pk, "exclude", initial)
    other = create_catalogue(owner, "Other")
    target = add(owner, other, [row("other")], "baseline").entries.get()
    with pytest.raises(DomainError, match="this catalogue"):
        action(owner, source, "merge", target_id=target.pk)


def test_merges_guard_dependents_and_export_fills_only_missing(owner):
    catalogue = create_catalogue(owner, "Private")
    target = add(
        owner, catalogue, [row("target", title="Canonical title")], "baseline"
    ).entries.get()
    source = add(
        owner, catalogue, [row("incoming", title="Variant title", doi="10.1234/test")]
    ).entries.get()
    action(owner, source, "merge", target_id=target.pk)
    target.refresh_from_db()
    selected, provenance = projection(target)
    assert selected["title"] == "Canonical title"
    assert selected["doi"] == "10.1234/test"
    assert provenance["doi"]["entry_id"] == str(source.pk)
    with pytest.raises(DomainError, match="merged into"):
        action(owner, target, "exclude")
    exported = list(csv.DictReader(io.StringIO(export_csv(owner, catalogue.pk))))
    assert len(exported) == 1
    assert exported[0]["entry_id"] == str(target.pk)
    assert exported[0]["doi"] == "10.1234/test"
    source_records = json.loads(exported[0]["source_records"])
    assert source_records == [
        {
            "entry_id": str(target.pk),
            "local_id": "target",
            "provider": "csv",
            "external_id": "target",
        },
        {
            "entry_id": str(source.pk),
            "local_id": "incoming",
            "provider": "csv",
            "external_id": "incoming",
        },
    ]
    changes = list(csv.DictReader(io.StringIO(export_changes(owner, catalogue.pk))))
    merge_event = next(event for event in changes if event["action"] == "merge")
    assert (merge_event["local_id"], merge_event["provider"], merge_event["external_id"]) == (
        "incoming",
        "csv",
        "incoming",
    )
    import_event = next(event for event in changes if event["action"] == "import")
    assert (import_event["local_id"], import_event["provider"], import_event["external_id"]) == (
        "",
        "",
        "",
    )
    action(owner, source, "reset")
    assert projection(target)[0].get("doi") is None


def test_corrections_keep_originals_and_require_reason(owner):
    catalogue = create_catalogue(owner, "Private")
    entry = add(owner, catalogue, [row("one")], "baseline").entries.get()
    with pytest.raises(DomainError):
        edit_fields(owner, entry.pk, {"title": "Better"}, "", catalogue.revision)
    edit_fields(
        owner,
        entry.pk,
        {"title": "Better", "journal": "A journal"},
        "Checked source",
        catalogue.revision,
    )
    entry.refresh_from_db()
    assert entry.normalized["title"] == "A study"
    assert effective(entry)["title_key"] == "better"
    assert effective(entry)["journal"] == "A journal"
    assert entry.events.get().before["overrides"] == {}


def test_export_formula_safety_unresolved_explicit_and_changes(owner):
    catalogue = create_catalogue(owner, "Private")
    entry = add(owner, catalogue, [row("one", title='=HYPERLINK("bad")')]).entries.get()
    assert len(list(csv.DictReader(io.StringIO(export_csv(owner, catalogue.pk))))) == 0
    exported = list(
        csv.DictReader(io.StringIO(export_csv(owner, catalogue.pk, include_unresolved=True)))
    )
    assert exported[0]["title"].startswith("'=")
    assert exported[0]["unresolved"] == "True"
    action(owner, entry, "exclude", reason="=unsafe")
    assert "'=unsafe" in export_changes(owner, catalogue.pk)
    assert (
        len(
            list(
                csv.DictReader(
                    io.StringIO(export_csv(owner, catalogue.pk, include_unresolved=True))
                )
            )
        )
        == 0
    )


def test_candidate_scope_and_conflict_reason(owner):
    catalogue = create_catalogue(owner, "Private")
    target = add(owner, catalogue, [row("target", doi="10.1234/one")], "baseline").entries.get()
    source = add(owner, catalogue, [row("incoming", doi="10.1234/two")]).entries.get()
    assert candidates(owner, source.pk)[0]["entry"].pk == target.pk
    with pytest.raises(DomainError, match="reason"):
        action(owner, source, "merge", target_id=target.pk)
    action(owner, source, "merge", target_id=target.pk, reason="Reviewed conflict")


def test_frozen_database_snapshots_and_audit(owner):
    catalogue = create_catalogue(owner, "Private")
    selection = add(owner, catalogue, [row("one")])
    with pytest.raises(DatabaseError), transaction.atomic():
        Entry.objects.filter(selection=selection).update(raw={})
    with pytest.raises(DatabaseError), transaction.atomic():
        AuditEvent.objects.filter(catalogue=catalogue).update(reason="rewrite")
    with pytest.raises(DatabaseError), transaction.atomic():
        selection.rows = []
        selection.save()


def test_selection_caps_and_whole_import_rollback(owner, monkeypatch):
    import catalogues.services as services

    catalogue = create_catalogue(owner, "Private")
    with pytest.raises(DomainError, match="100"):
        create_selection(owner, catalogue.pk, "incoming", [row(str(i)) for i in range(101)])
    monkeypatch.setattr(services, "MAX_ENTRIES", 1)
    selection = create_selection(owner, catalogue.pk, "baseline", [row("a"), row("b")])
    with pytest.raises(DomainError, match="at most"):
        confirm_selection(owner, selection.pk, catalogue.revision)
    assert catalogue.entries.count() == 0
    selection.refresh_from_db()
    assert not selection.consumed


@pytest.mark.parametrize("root_doi", ["", "10.1234/b"])
def test_merge_checks_conflicting_child_even_when_root_doi_missing_or_matches(owner, root_doi):
    catalogue = create_catalogue(owner, "Private")
    root = add(owner, catalogue, [row("root", doi=root_doi)], "baseline").entries.get()
    first = add(owner, catalogue, [row("first", doi="10.1234/a")]).entries.get()
    action(owner, first, "merge", target_id=root.pk, reason="First merge reviewed")
    incoming = add(owner, catalogue, [row("incoming", doi="10.1234/b")]).entries.get()
    comparison = candidates(owner, incoming.pk)[0]["comparison"]
    assert "different_doi" in comparison["warnings"]
    child_evidence = next(
        item for item in comparison["group_evidence"] if item["entry_id"] == str(first.pk)
    )
    assert child_evidence["signals"]["doi"] == "different"
    with pytest.raises(DomainError, match="reason"):
        action(owner, incoming, "merge", target_id=root.pk)
    action(owner, incoming, "merge", target_id=root.pk, reason="All group identifiers reviewed")


def test_candidate_uses_doi_from_merged_projection(owner):
    catalogue = create_catalogue(owner, "Private")
    root = add(owner, catalogue, [row("root", title="Initial root")], "baseline").entries.get()
    first = add(
        owner, catalogue, [row("first", title="Initial root", doi="10.1234/a")]
    ).entries.get()
    action(owner, first, "merge", target_id=root.pk)
    incoming = add(
        owner, catalogue, [row("incoming", title="Completely different evidence", doi="10.1234/a")]
    ).entries.get()
    comparison = candidates(owner, incoming.pk)[0]["comparison"]
    assert comparison["signals"]["doi"] == "identical"
