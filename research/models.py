import uuid

from django.conf import settings
from django.db import models, router, transaction

from research.source_fields import SourceJSONField
from research.source_storage import SOURCE_FIELDS, compact, references

from .states import Stage, Status


class Dossier(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    question = models.TextField()
    year_from = models.PositiveIntegerField(default=2020)
    limit = models.PositiveSmallIntegerField(default=12)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    focus = models.TextField(blank=True)
    report_focus = models.TextField(blank=True)
    use_fulltext = models.BooleanField(default=False)
    stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.PLAN)
    plan = models.JSONField(default=dict)
    papers = SourceJSONField(default=list)
    selected = models.JSONField(default=list)
    report = models.JSONField(default=dict)
    report_papers = SourceJSONField(default=list)
    report_selected = models.JSONField(default=list)
    versions = SourceJSONField(default=list)
    investigation = models.JSONField(default=dict)
    events = models.JSONField(default=list)
    error = models.TextField(blank=True)
    run_id = models.UUIDField(default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="research_queue_idx"),
            models.Index(fields=["owner", "-created_at"], name="research_owner_recent_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=Status.values), name="research_valid_status"
            ),
            models.CheckConstraint(
                condition=models.Q(stage__in=Stage.values), name="research_valid_stage"
            ),
            models.CheckConstraint(
                condition=models.Q(limit__gte=1, limit__lte=20), name="research_valid_limit"
            ),
        ]

    def save(self, *args, **kwargs):
        """Persist evidence once; report histories retain immutable references."""
        update_fields = kwargs.get("update_fields")
        using = kwargs.get("using") or router.db_for_write(type(self), instance=self)
        originals = {}
        snapshots = {}
        for name in SOURCE_FIELDS:
            if name in self.__dict__ and (update_fields is None or name in update_fields):
                originals[name] = self.__dict__[name]
                self.__dict__[name] = compact(originals[name], snapshots)
        referenced = set()
        for name in originals:
            referenced.update(references(self.__dict__[name]))
        try:
            self.__dict__["_saving_source_references"] = True
            with transaction.atomic(using=using):
                super().save(*args, **kwargs)
                if snapshots:
                    SourceSnapshot.objects.using(using).bulk_create(
                        [
                            SourceSnapshot(dossier_id=self.pk, digest=digest, payload=payload)
                            for digest, payload in snapshots.items()
                        ],
                        ignore_conflicts=True,
                    )
                if referenced:
                    present = set(
                        SourceSnapshot.objects.using(using)
                        .filter(dossier_id=self.pk, digest__in=referenced)
                        .values_list("digest", flat=True)
                    )
                    if referenced - present:
                        raise ValueError(
                            "Cannot save a dossier with missing private source snapshots"
                        )
        finally:
            self.__dict__.pop("_saving_source_references", None)
            self.__dict__.update(originals)

    @property
    def report_stale(self):
        return bool(self.report) and (
            set(self.selected) != set(self.report_selected) or self.focus != self.report_focus
        )


class ResearchRun(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    dossier = models.ForeignKey(Dossier, on_delete=models.CASCADE, related_name="runs")
    stage = models.CharField(max_length=20)
    focus = models.TextField(blank=True)
    status = models.CharField(max_length=20, default="running")
    metrics = models.JSONField(default=list)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]


class UsageBucket(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    started_at = models.DateTimeField(db_index=True)
    count = models.PositiveIntegerField(default=0)


class SourceSnapshot(models.Model):
    """Private immutable evidence; revisions reference rather than duplicate it."""

    dossier = models.ForeignKey(Dossier, on_delete=models.CASCADE, related_name="source_snapshots")
    digest = models.CharField(max_length=64)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["dossier", "digest"], name="research_source_digest_unique"
            )
        ]
