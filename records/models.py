import uuid

from django.contrib.postgres.indexes import GistIndex
from django.db import models
from django.db.models import F, Q


class CanonicalPublication(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    revision = models.PositiveIntegerField(default=1)
    state = models.CharField(max_length=20, default="active", db_index=True)
    successors = models.JSONField(default=list)
    projection = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class SourceRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=32)
    external_id = models.CharField(max_length=512)
    current_version = models.ForeignKey(
        "SourceRecordVersion", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    publication = models.ForeignKey(
        CanonicalPublication, on_delete=models.PROTECT, related_name="records"
    )
    doi = models.TextField(blank=True, db_index=True)
    title_key = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "external_id"], name="source_identity_unique"
            )
        ]
        indexes = [
            GistIndex(fields=["title_key"], opclasses=["gist_trgm_ops"], name="source_title_trgm")
        ]


class SourceRecordVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    record = models.ForeignKey(SourceRecord, on_delete=models.PROTECT, related_name="versions")
    raw = models.JSONField()
    normalized = models.JSONField()
    content_hash = models.CharField(max_length=64)
    normalization_version = models.CharField(max_length=32, default="1")
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["record", "content_hash"], name="source_content_unique")
        ]
        ordering = ["-fetched_at"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Source versions are immutable.")
        return super().save(*args, **kwargs)


class CandidatePair(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    left = models.ForeignKey(SourceRecord, on_delete=models.PROTECT, related_name="left_pairs")
    right = models.ForeignKey(SourceRecord, on_delete=models.PROTECT, related_name="right_pairs")
    revision = models.PositiveIntegerField(default=1)
    state = models.CharField(max_length=32, default="pending", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["left", "right"], name="candidate_unique"),
            models.CheckConstraint(condition=Q(left__lt=F("right")), name="candidate_ordered"),
        ]


class MatchProposal(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pair = models.ForeignKey(CandidatePair, on_delete=models.PROTECT, related_name="proposals")
    left_version = models.ForeignKey(
        SourceRecordVersion, on_delete=models.PROTECT, related_name="+"
    )
    right_version = models.ForeignKey(
        SourceRecordVersion, on_delete=models.PROTECT, related_name="+"
    )
    method = models.CharField(max_length=64, default="lexical-v1")
    config = models.JSONField(default=dict)
    signals = models.JSONField(default=dict)
    warnings = models.JSONField(default=list)
    ranking_score = models.FloatField(null=True)
    recommendation = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ReviewDecision(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pair = models.ForeignKey(CandidatePair, on_delete=models.PROTECT, related_name="decisions")
    proposal = models.ForeignKey(MatchProposal, on_delete=models.PROTECT, related_name="decisions")
    action = models.CharField(max_length=16)
    actor = models.CharField(max_length=150)
    reason = models.TextField(blank=True)
    expected_revision = models.PositiveIntegerField()
    idempotency_key = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    withdrawal_of = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="withdrawal"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["actor", "idempotency_key"], name="decision_idempotency_unique"
            )
        ]


class Membership(models.Model):
    publication = models.ForeignKey(
        CanonicalPublication, on_delete=models.PROTECT, related_name="memberships"
    )
    record = models.ForeignKey(SourceRecord, on_delete=models.PROTECT, related_name="memberships")
    origin = models.CharField(max_length=64, default="ingest")
    valid_from = models.DateTimeField(auto_now_add=True)
    valid_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["record"],
                condition=Q(valid_until__isnull=True),
                name="one_active_membership",
            )
        ]


class ImportRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=32)
    profile = models.JSONField(default=dict)
    status = models.CharField(max_length=24, default="queued", db_index=True)
    cursor = models.JSONField(default=dict)
    counters = models.JSONField(default=dict)
    lease_owner = models.CharField(max_length=64, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    idempotency_key = models.CharField(max_length=128, unique=True, null=True, blank=True)
    request_hash = models.CharField(max_length=64, blank=True)
    error = models.TextField(blank=True)


class ImportFailure(models.Model):
    run = models.ForeignKey(ImportRun, on_delete=models.PROTECT, related_name="failures")
    external_id = models.CharField(max_length=512, blank=True)
    raw = models.JSONField(default=dict)
    code = models.CharField(max_length=64)
    message = models.TextField()
    attempts = models.PositiveIntegerField(default=1)
    retryable = models.BooleanField(default=True)
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class BenchmarkRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    manifest = models.JSONField(default=dict)
    git_revision = models.CharField(max_length=64, blank=True)
    config = models.JSONField(default=dict)
    metrics = models.JSONField(default=dict)
    environment = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
