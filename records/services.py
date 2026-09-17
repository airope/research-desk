"""Transactional domain operations.

A transaction advisory lock serializes graph mutation for the bounded local
corpus. This intentionally trades write throughput for simple, auditable
cross-pair conflict safety; reads and remote fetching remain concurrent.
"""

import hashlib
import json

from django.contrib.postgres.search import TrigramDistance
from django.db import connection, transaction
from django.db.models import F, Q
from django.utils import timezone

from .matching import CONFIG, compare_metadata
from .models import (
    CandidatePair,
    CanonicalPublication,
    MatchProposal,
    Membership,
    ReviewDecision,
    SourceRecord,
    SourceRecordVersion,
)
from .normalization import NORMALIZATION_VERSION, normalize_record


class DomainError(Exception):
    def __init__(self, code, message, status=409):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


def _hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _lock():
    if connection.vendor != "postgresql":
        raise RuntimeError("PostgreSQL is required for domain consistency.")
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(73421901)")


def _project(publication):
    records = list(publication.records.select_related("current_version").all())
    records.sort(
        key=lambda r: ({"crossref": 0, "openalex": 1}.get(r.provider, 2), r.provider, r.external_id)
    )
    projection = {}
    for field in ("doi", "title", "authors", "year", "dates", "type", "abstract"):
        for record in records:
            if record.current_version and record.current_version.normalized.get(field):
                projection[field] = {
                    "value": record.current_version.normalized[field],
                    "version_id": str(record.current_version_id),
                    "path": f"normalized.{field}",
                    "policy": "crossref-first-v1",
                }
                break
    publication.projection = projection
    publication.revision += 1
    publication.save(update_fields=["projection", "revision", "updated_at"])


@transaction.atomic
def ingest_record(provider, external_id, raw, normalized=None):
    if not provider or not external_id or len(str(external_id)) > 512:
        raise ValueError("Provider and a bounded external ID are required.")
    normalized = normalize_record(provider, raw) if normalized is None else normalized
    content_hash = _hash(
        {"raw": raw, "normalized": normalized, "normalization_version": NORMALIZATION_VERSION}
    )
    _lock()
    record = SourceRecord.objects.filter(provider=provider, external_id=str(external_id)).first()
    created = record is None
    if created:
        publication = CanonicalPublication.objects.create()
        record = SourceRecord.objects.create(
            provider=provider, external_id=str(external_id), publication=publication
        )
        Membership.objects.create(record=record, publication=publication)
    elif record.current_version and record.current_version.content_hash == content_hash:
        return record, "unchanged"
    version, _ = SourceRecordVersion.objects.get_or_create(
        record=record,
        content_hash=content_hash,
        defaults={
            "raw": raw,
            "normalized": normalized,
            "normalization_version": NORMALIZATION_VERSION,
        },
    )
    record.current_version = version
    record.doi = normalized.get("doi") or ""
    record.title_key = normalized.get("title_key") or ""
    record.save(update_fields=["current_version", "doi", "title_key", "updated_at"])
    _project(record.publication)
    group_ids = SourceRecord.objects.filter(publication=record.publication).values_list(
        "pk", flat=True
    )
    CandidatePair.objects.filter(Q(left_id__in=group_ids) | Q(right_id__in=group_ids)).update(
        revision=F("revision") + 1
    )
    for pair in CandidatePair.objects.filter(Q(left=record) | Q(right=record)).order_by("id"):
        compare_pair(pair)
    return record, "created" if created else "updated"


@transaction.atomic
def compare_pair(pair_or_id):
    _lock()
    pair_id = getattr(pair_or_id, "pk", pair_or_id)
    pair = CandidatePair.objects.select_related(
        "left__current_version", "right__current_version"
    ).get(pk=pair_id)
    latest = pair.proposals.first()
    if (
        latest
        and latest.left_version_id == pair.left.current_version_id
        and latest.right_version_id == pair.right.current_version_id
        and latest.config == CONFIG
    ):
        return latest
    result = compare_metadata(
        pair.left.current_version.normalized, pair.right.current_version.normalized
    )
    proposal = MatchProposal.objects.create(
        pair=pair,
        left_version=pair.left.current_version,
        right_version=pair.right.current_version,
        config=CONFIG,
        **result,
    )
    if latest:
        pair.revision += 1
        pair.state = "needs_reassessment" if pair.decisions.exists() else result["recommendation"]
    else:
        pair.state = result["recommendation"]
    pair.save(update_fields=["revision", "state", "updated_at"])
    return proposal


def candidate_ids(record, k=20, pool=None):
    if not 1 <= k <= 200:
        raise ValueError("K must be between 1 and 200.")
    others = (SourceRecord.objects.all() if pool is None else pool).exclude(pk=record.pk)
    ids = set()
    if record.doi:
        ids.update(others.filter(doi=record.doi).values_list("pk", flat=True))
    if record.title_key:
        ids.update(
            others.exclude(title_key="")
            .annotate(distance=TrigramDistance("title_key", record.title_key))
            .order_by("distance", "provider", "external_id")
            .values_list("pk", flat=True)[:k]
        )
    return ids


@transaction.atomic
def generate_candidates(k=20):
    if not 1 <= k <= 200:
        raise ValueError("K must be between 1 and 200.")
    _lock()
    count = 0
    for record in SourceRecord.objects.order_by("id").iterator():
        for other_id in sorted(candidate_ids(record, k)):
            left, right = sorted([record.pk, other_id])
            pair, created = CandidatePair.objects.get_or_create(left_id=left, right_id=right)
            count += int(created)
            compare_pair(pair)
    return count


def _active_decisions():
    return ReviewDecision.objects.filter(withdrawal__isnull=True).exclude(action="withdraw")


def _components(record_ids, excluded=None):
    groups = {pk: {pk} for pk in record_ids}
    edges = _active_decisions().filter(
        action="accept", pair__left_id__in=record_ids, pair__right_id__in=record_ids
    )
    if excluded:
        edges = edges.exclude(pk=excluded)
    for left, right in edges.values_list("pair__left_id", "pair__right_id"):
        merged = groups[left] | groups[right]
        for pk in merged:
            groups[pk] = merged
    unique = {frozenset(value) for value in groups.values()}
    return sorted(unique, key=lambda group: str(min(group)))


def _regroup(publication_ids, origin):
    records = list(SourceRecord.objects.filter(publication_id__in=publication_ids).order_by("id"))
    record_ids = {r.pk for r in records}
    CandidatePair.objects.filter(Q(left_id__in=record_ids) | Q(right_id__in=record_ids)).update(
        revision=F("revision") + 1
    )
    groups = _components(record_ids)
    old_groups = {pk: {r.pk for r in records if r.publication_id == pk} for pk in publication_ids}
    mapping = {}
    for group in groups:
        existing = next((pk for pk, members in old_groups.items() if members == group), None)
        publication = (
            CanonicalPublication.objects.get(pk=existing)
            if existing
            else CanonicalPublication.objects.create()
        )
        for pk in group:
            mapping[pk] = publication.pk
        if not existing:
            Membership.objects.filter(record_id__in=group, valid_until__isnull=True).update(
                valid_until=timezone.now()
            )
            SourceRecord.objects.filter(pk__in=group).update(publication=publication)
            Membership.objects.bulk_create(
                [Membership(record_id=pk, publication=publication, origin=origin) for pk in group]
            )
        _project(publication)
    for pk, members in old_groups.items():
        successors = sorted({str(mapping[r]) for r in members})
        if successors != [str(pk)]:
            CanonicalPublication.objects.filter(pk=pk).update(
                state="replaced", successors=successors
            )


def _idempotent(actor, key, payload):
    if not key or len(key) > 128:
        raise DomainError("invalid_idempotency_key", "A key of 1–128 characters is required.", 400)
    digest = _hash(payload)
    prior = ReviewDecision.objects.filter(actor=actor, idempotency_key=key).first()
    if prior and prior.request_hash != digest:
        raise DomainError(
            "idempotency_conflict", "This key was already used for a different request."
        )
    return prior, digest


def _check_revision(pair, expected):
    if pair.revision != expected:
        raise DomainError("stale_revision", "The evidence changed. Reload before deciding.")


@transaction.atomic
def decide(pair_id, action, actor, reason="", expected_revision=None, idempotency_key=""):
    _lock()
    actor = str(actor)
    reason = reason.strip()
    if action not in ("accept", "reject", "defer"):
        raise DomainError("invalid_action", "Choose accept, reject, or defer.", 400)
    payload = {
        "pair": str(pair_id),
        "action": action,
        "reason": reason,
        "expected_revision": expected_revision,
    }
    prior, digest = _idempotent(actor, idempotency_key, payload)
    if prior:
        return prior
    pair = CandidatePair.objects.select_for_update().select_related("left", "right").get(pk=pair_id)
    _check_revision(pair, expected_revision)
    proposal = pair.proposals.first()
    if not proposal:
        raise DomainError("missing_proposal", "Generate comparison evidence first.")
    if _active_decisions().filter(pair=pair, action__in=["accept", "reject"]).exists():
        raise DomainError("active_decision", "Withdraw the active decision before replacing it.")
    publication_ids = {pair.left.publication_id, pair.right.publication_id}
    records = list(
        SourceRecord.objects.filter(publication_id__in=publication_ids).select_related(
            "current_version"
        )
    )
    ids = [r.pk for r in records]
    if action == "accept":
        if (
            _active_decisions()
            .filter(action="reject", pair__left_id__in=ids, pair__right_id__in=ids)
            .exists()
        ):
            raise DomainError(
                "group_rejection", "An active rejection inside this group must be withdrawn first."
            )
        dois = {r.doi for r in records if r.doi}
        types = {
            r.current_version.normalized.get("type")
            for r in records
            if r.current_version.normalized.get("type")
        }
        if (len(dois) > 1 or len(types) > 1 or proposal.warnings) and not reason:
            raise DomainError(
                "reason_required", "Accepting conflicting evidence requires a reason.", 400
            )
    if action == "reject":
        if pair.left.publication_id == pair.right.publication_id:
            raise DomainError(
                "group_connected",
                "Withdraw accepted links connecting these records before rejecting them.",
            )
        if proposal.signals.get("doi") == "identical" and not reason:
            raise DomainError(
                "reason_required", "Rejecting an identical DOI requires a reason.", 400
            )
    decision = ReviewDecision.objects.create(
        pair=pair,
        proposal=proposal,
        actor=actor,
        action=action,
        reason=reason,
        expected_revision=expected_revision,
        idempotency_key=idempotency_key,
        request_hash=digest,
    )
    pair.state = {"accept": "accepted", "reject": "rejected", "defer": "deferred"}[action]
    pair.revision += 1
    pair.save(update_fields=["state", "revision", "updated_at"])
    if action == "accept":
        _regroup(publication_ids, f"decision:{decision.pk}")
    return decision


@transaction.atomic
def withdrawal_preview(decision_id):
    _lock()
    decision = ReviewDecision.objects.select_related("pair__left", "pair__right").get(
        pk=decision_id
    )
    ids = set(
        SourceRecord.objects.filter(
            publication_id__in=[
                decision.pair.left.publication_id,
                decision.pair.right.publication_id,
            ]
        ).values_list("pk", flat=True)
    )
    groups = _components(ids, excluded=decision.pk)
    return {
        "groups": [[str(pk) for pk in sorted(group)] for group in groups],
        "will_split": decision.action == "accept" and len(groups) > 1,
        "remaining_links": list(
            _active_decisions()
            .filter(action="accept", pair__left_id__in=ids, pair__right_id__in=ids)
            .exclude(pk=decision.pk)
            .values_list("id", flat=True)
        ),
        "expected_revision": decision.pair.revision,
    }


@transaction.atomic
def withdraw(decision_id, actor, reason="", expected_revision=None, idempotency_key=""):
    _lock()
    actor = str(actor)
    reason = reason.strip()
    payload = {
        "withdraw": str(decision_id),
        "reason": reason,
        "expected_revision": expected_revision,
    }
    prior, digest = _idempotent(actor, idempotency_key, payload)
    if prior:
        return prior
    if not reason:
        raise DomainError("reason_required", "Withdrawal requires a reason.", 400)
    original = ReviewDecision.objects.select_related("pair__left", "pair__right", "proposal").get(
        pk=decision_id
    )
    pair = original.pair
    _check_revision(pair, expected_revision)
    if original.action == "withdraw" or hasattr(original, "withdrawal"):
        raise DomainError("already_withdrawn", "This decision cannot be withdrawn again.")
    decision = ReviewDecision.objects.create(
        pair=pair,
        proposal=original.proposal,
        action="withdraw",
        actor=actor,
        reason=reason,
        expected_revision=expected_revision,
        idempotency_key=idempotency_key,
        request_hash=digest,
        withdrawal_of=original,
    )
    pair.revision += 1
    remaining = _active_decisions().filter(pair=pair)
    controlling = (
        remaining.filter(action__in=["accept", "reject"]).first()
        or remaining.filter(action="defer").first()
    )
    latest_proposal = pair.proposals.first()
    if controlling and controlling.proposal_id == latest_proposal.pk:
        pair.state = {"accept": "accepted", "reject": "rejected", "defer": "deferred"}[
            controlling.action
        ]
    else:
        pair.state = "needs_reassessment"
    pair.save(update_fields=["revision", "state", "updated_at"])
    if original.action == "accept":
        _regroup({pair.left.publication_id, pair.right.publication_id}, f"withdrawal:{decision.pk}")
    return decision
