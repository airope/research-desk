"""Persisted states shared by commands, workers and database constraints."""

from django.db.models import TextChoices


class Status(TextChoices):
    DRAFT = "draft", "Draft"
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class Stage(TextChoices):
    PLAN = "plan", "Plan"
    SEARCH = "search", "Search"
    FULLTEXT = "fulltext", "Read PDFs"
    SYNTHESIZE = "synthesize", "Synthesize"
    INVESTIGATE = "investigate", "Investigate"
