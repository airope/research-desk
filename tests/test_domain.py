import pytest
from django.db import IntegrityError, transaction

from records.matching import compare_metadata
from records.models import (
    CandidatePair,
    CanonicalPublication,
    Membership,
    ReviewDecision,
    SourceRecord,
    SourceRecordVersion,
)
from records.normalization import normalize_doi, normalize_title
from records.services import (
    DomainError,
    compare_pair,
    decide,
    generate_candidates,
    ingest_record,
    withdraw,
    withdrawal_preview,
)


def record(key, doi="10.1234/example", title="A scientific result", kind="journal-article"):
    return ingest_record("crossref", key, {"DOI": doi, "title": [title], "type": kind})[0]


def pair(a, b):
    a, b = sorted([a, b], key=lambda r: r.pk)
    value = CandidatePair.objects.create(left=a, right=b)
    compare_pair(value)
    value.refresh_from_db()
    return value


def accept(value, key, reason=""):
    value.refresh_from_db()
    return decide(value.pk, "accept", "curator", reason, value.revision, key)


def test_normalization_retains_semantics():
    assert normalize_doi("https://doi.org/10.1234/ABC.") == "10.1234/abc."
    assert normalize_doi("not-a-doi") == ""
    assert normalize_title("  NOT  １２ particles ") == "not 12 particles"
    assert normalize_title(normalize_title("ÉCOLE")) == normalize_title("ÉCOLE")
    result = compare_metadata(
        {"title_key": "particles exist"}, {"title_key": "particles do not exist"}
    )
    assert "negation_differs" in result["warnings"]
    assert result["signals"]["doi"] == "missing"


@pytest.mark.django_db
def test_import_versioning_and_return_to_earlier_content():
    a = record("one")
    assert ingest_record(a.provider, a.external_id, a.current_version.raw)[1] == "unchanged"
    old = a.current_version_id
    record("one", title="Corrected title")
    a.refresh_from_db()
    assert a.versions.count() == 2
    record("one")
    a.refresh_from_db()
    assert a.current_version_id == old
    assert a.versions.count() == 2
    assert a.publication.projection["title"]["version_id"] == str(old)


@pytest.mark.django_db
def test_history_database_immutable():
    a = record("immutable")
    with pytest.raises(Exception), transaction.atomic():
        SourceRecordVersion.objects.filter(pk=a.current_version_id).update(raw={})


@pytest.mark.django_db
def test_accept_withdraw_preserves_sources_and_old_identifiers():
    a, b = record("a"), record("b")
    old_ids = {a.publication_id, b.publication_id}
    candidate = pair(a, b)
    decision = accept(candidate, "accept")
    a.refresh_from_db()
    b.refresh_from_db()
    assert a.publication_id == b.publication_id
    assert CanonicalPublication.objects.filter(pk__in=old_ids, state="replaced").count() == 2
    assert withdrawal_preview(decision.pk)["will_split"]
    candidate.refresh_from_db()
    withdraw(decision.pk, "curator", "Incorrect association", candidate.revision, "withdraw")
    a.refresh_from_db()
    b.refresh_from_db()
    assert a.publication_id != b.publication_id
    assert SourceRecord.objects.count() == SourceRecordVersion.objects.count() == 2
    assert Membership.objects.filter(valid_until__isnull=True).count() == 2
    assert ReviewDecision.objects.count() == 2


@pytest.mark.django_db
def test_redundant_link_withdrawal_retains_group():
    a, b, c = record("a"), record("b"), record("c")
    ab, bc, ac = pair(a, b), pair(b, c), pair(a, c)
    decision = accept(ab, "ab")
    accept(bc, "bc")
    accept(ac, "ac")
    assert not withdrawal_preview(decision.pk)["will_split"]
    ab.refresh_from_db()
    withdraw(decision.pk, "curator", "Remove redundant evidence", ab.revision, "undo")
    assert SourceRecord.objects.values("publication_id").distinct().count() == 1


@pytest.mark.django_db
def test_stale_and_idempotent_writes():
    value = pair(record("a"), record("b"))
    decision = accept(value, "key")
    assert decide(value.pk, "accept", "curator", "", value.revision, "key").pk == decision.pk
    with pytest.raises(DomainError, match="different request"):
        decide(value.pk, "reject", "curator", "different", value.revision, "key")
    with pytest.raises(DomainError, match="Reload"):
        decide(value.pk, "defer", "other", "", value.revision, "new")


@pytest.mark.django_db
def test_group_rejection_cannot_be_overridden_transitively():
    a, b, c = record("a"), record("b"), record("c")
    ab, bc, ac = pair(a, b), pair(b, c), pair(a, c)
    decide(ac.pk, "reject", "curator", "Distinct publications", ac.revision, "reject")
    accept(ab, "ab")
    with pytest.raises(DomainError, match="active rejection"):
        accept(bc, "bc", "Override")


@pytest.mark.django_db
def test_group_doi_conflict_requires_reason_and_updates_preserve_decision():
    a, b, c = record("a"), record("b", doi=""), record("c", doi="10.1234/other")
    ab, bc = pair(a, b), pair(b, c)
    accepted = accept(ab, "ab")
    with pytest.raises(DomainError, match="requires a reason"):
        accept(bc, "bc")
    record("a", doi="10.1234/changed")
    ab.refresh_from_db()
    assert ab.state == "needs_reassessment"
    assert ab.decisions.filter(pk=accepted.pk).exists()
    assert ab.proposals.count() == 2


@pytest.mark.django_db
def test_exact_doi_candidates_not_limited_by_k():
    records = [record(str(i), title=f"Unrelated title {i}") for i in range(5)]
    assert generate_candidates(k=1) == 10
    assert generate_candidates(k=1) == 0
    assert CandidatePair.objects.count() == 10
    with pytest.raises(IntegrityError), transaction.atomic():
        CandidatePair.objects.create(left=records[0], right=records[0])


@pytest.mark.django_db
def test_preview_invalidated_when_another_link_changes_group():
    a, b, c = record("a"), record("b"), record("c")
    ab, bc = pair(a, b), pair(b, c)
    decision = accept(ab, "ab")
    preview = withdrawal_preview(decision.pk)
    accept(bc, "bc")
    with pytest.raises(DomainError, match="Reload"):
        withdraw(decision.pk, "curator", "Split", preview["expected_revision"], "undo")


@pytest.mark.django_db
def test_unchanged_import_does_not_reopen_rejection():
    a, b = record("a"), record("b")
    candidate = pair(a, b)
    decide(candidate.pk, "reject", "curator", "Wrong DOI assignment", candidate.revision, "reject")
    candidate.refresh_from_db()
    revision = candidate.revision
    record("a")
    generate_candidates()
    candidate.refresh_from_db()
    assert candidate.state == "rejected"
    assert candidate.revision == revision


@pytest.mark.django_db
def test_equal_title_candidates_use_source_identity_ties_not_random_uuid():
    from records.services import candidate_ids

    query = record("query", doi="", title="Identical title")
    others = [record(f"candidate-{i:02}", doi="", title="Identical title") for i in range(25)]
    selected = candidate_ids(query, k=20)
    assert selected == {r.pk for r in others[:20]}


@pytest.mark.django_db
def test_withdrawing_old_defer_preserves_active_acceptance_state():
    candidate = pair(record("a"), record("b"))
    deferred = decide(candidate.pk, "defer", "curator", "", candidate.revision, "defer")
    accept(candidate, "accept")
    candidate.refresh_from_db()
    withdraw(deferred.pk, "curator", "Remove obsolete deferral", candidate.revision, "undo-defer")
    candidate.refresh_from_db()
    assert candidate.state == "accepted"


@pytest.mark.django_db
def test_withdrawing_old_defer_preserves_stale_evidence_state():
    a, b = record("a"), record("b")
    candidate = pair(a, b)
    deferred = decide(candidate.pk, "defer", "curator", "", candidate.revision, "defer")
    accept(candidate, "accept")
    record("a", title="Changed evidence")
    candidate.refresh_from_db()
    withdraw(deferred.pk, "curator", "Remove obsolete deferral", candidate.revision, "undo-defer")
    candidate.refresh_from_db()
    assert candidate.state == "needs_reassessment"


@pytest.mark.parametrize(
    "raw",
    [
        {"author": {"family": "Not a list"}},
        {"author": [42]},
        {"author": [{"given": ["Not text"]}]},
        {"published": {"date-parts": [["2025"]]}},
        {"published": {"date-parts": []}},
        {"published": {"date-parts": [[2025, 13]]}},
        {"type": ["journal-article"]},
        {"year": "2025"},
    ],
)
def test_malformed_nested_metadata_raises_visible_validation_failure(raw):
    from records.normalization import normalize_record

    with pytest.raises(ValueError):
        normalize_record("crossref", raw)
