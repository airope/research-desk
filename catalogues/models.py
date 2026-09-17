import uuid

from django.conf import settings
from django.db import models


class Catalogue(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    name = models.CharField(max_length=200)
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Selection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    catalogue = models.ForeignKey(Catalogue, on_delete=models.CASCADE, related_name="selections")
    kind = models.CharField(max_length=16)
    rows = models.JSONField(default=list)
    errors = models.JSONField(default=list)
    provenance = models.JSONField(default=dict)
    consumed = models.BooleanField(default=False)
    summary = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)


class Entry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    catalogue = models.ForeignKey(Catalogue, on_delete=models.CASCADE, related_name="entries")
    selection = models.ForeignKey(Selection, on_delete=models.PROTECT, related_name="entries")
    position = models.PositiveIntegerField()
    origin = models.CharField(max_length=16)
    provider = models.CharField(max_length=32)
    external_id = models.CharField(max_length=512, blank=True)
    local_id = models.CharField(max_length=512, blank=True)
    raw = models.JSONField(default=dict)
    normalized = models.JSONField(default=dict)
    status = models.CharField(max_length=16, default="pending", db_index=True)
    merge_target = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="merged_entries"
    )
    overrides = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["selection", "position"], name="catalogue_selection_position"
            )
        ]


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    catalogue = models.ForeignKey(Catalogue, on_delete=models.PROTECT, related_name="events")
    entry = models.ForeignKey(Entry, null=True, on_delete=models.PROTECT, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=24)
    reason = models.TextField(blank=True)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    idempotency_key = models.CharField(max_length=128, null=True, blank=True)
    request_hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["catalogue", "idempotency_key"], name="catalogue_action_idempotency"
            )
        ]
