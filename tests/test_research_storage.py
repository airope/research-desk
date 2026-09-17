import copy

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from research.models import Dossier, SourceSnapshot
from research.source_storage import REFERENCE_KEY

pytestmark = pytest.mark.django_db
PAPER = {
    "id": "123",
    "title": "Evidence",
    "abstract": "original abstract",
    "document": {"pages": [{"page": 1, "text": "immutable page text"}]},
}


def make_dossier():
    user = User.objects.create_user(username="storage-owner")
    return Dossier.objects.create(owner=user, question="test", papers=[copy.deepcopy(PAPER)])


def test_sources_deduplicate_across_reports_and_versions():
    dossier = make_dossier()
    dossier.report_papers = copy.deepcopy(dossier.papers)
    dossier.versions = [{"papers": copy.deepcopy(dossier.papers)} for _ in range(5)]
    dossier.save()
    assert SourceSnapshot.objects.filter(dossier=dossier).count() == 1
    raw = Dossier.objects.filter(pk=dossier.pk).values("papers", "report_papers", "versions").get()
    assert REFERENCE_KEY in raw["papers"][0]
    assert "document" not in raw["papers"][0]
    loaded = Dossier.objects.get(pk=dossier.pk)
    assert loaded.papers == [PAPER]
    assert loaded.report_papers == [PAPER]
    assert loaded.versions[0]["papers"] == [PAPER]


def test_revised_text_preserves_previous_report_and_private_snapshots():
    dossier = make_dossier()
    dossier.report_papers = copy.deepcopy(dossier.papers)
    dossier.save()
    dossier.papers[0]["document"]["pages"][0]["text"] = "corrected page"
    dossier.save(update_fields=["papers"])
    loaded = Dossier.objects.get(pk=dossier.pk)
    assert loaded.papers[0]["document"]["pages"][0]["text"] == "corrected page"
    assert loaded.report_papers == [PAPER]
    assert SourceSnapshot.objects.filter(dossier=dossier).count() == 2
    loaded.delete()
    assert not SourceSnapshot.objects.exists()


def test_summary_reads_and_progress_updates_do_not_load_sources():
    dossier = make_dossier()
    with CaptureQueriesContext(connection) as queries:
        loaded = Dossier.objects.only("id", "status").get(pk=dossier.pk)
        loaded.status = "ready"
        loaded.save(update_fields=["status"])
    assert not any("research_sourcesnapshot" in item["sql"] for item in queries)
    assert Dossier.objects.get(pk=dossier.pk).papers == [PAPER]


def test_compaction_is_idempotent_and_supports_legacy_inline_sources():
    dossier = make_dossier()
    # Simulate a row written before source storage was introduced.
    Dossier.objects.filter(pk=dossier.pk).update(papers=[PAPER], versions=[{"papers": [PAPER]}])
    call_command("compact_research_sources", dossier=str(dossier.pk))
    call_command("compact_research_sources", dossier=str(dossier.pk))
    loaded = Dossier.objects.get(pk=dossier.pk)
    assert loaded.papers == [PAPER]
    assert loaded.versions[0]["papers"] == [PAPER]
    assert SourceSnapshot.objects.filter(dossier=dossier).count() == 1


def test_references_cannot_read_other_dossier_payloads():
    dossier = make_dossier()
    other = Dossier.objects.create(owner=dossier.owner, question="other")
    digest = SourceSnapshot.objects.get(dossier=dossier).digest
    Dossier.objects.filter(pk=other.pk).update(papers=[{REFERENCE_KEY: digest}])
    with pytest.raises(RuntimeError, match="Missing immutable"):
        _ = Dossier.objects.get(pk=other.pk).papers


def test_save_rejects_dangling_source_reference_atomically():
    dossier = make_dossier()
    dossier.papers = [{"id": "broken", "title": "Bad", REFERENCE_KEY: "0" * 64}]
    with pytest.raises(ValueError, match="missing private"):
        dossier.save(update_fields=["papers"])
    assert Dossier.objects.get(pk=dossier.pk).papers == [PAPER]


def test_pruning_preserves_history_and_removes_only_abandoned_revisions():
    dossier = make_dossier()
    dossier.versions = [{"papers": copy.deepcopy(dossier.papers)}]
    dossier.papers[0]["abstract"] = "abandoned revision"
    dossier.save()
    abandoned = SourceSnapshot.objects.get(payload__abstract="abandoned revision").digest
    dossier.papers[0]["abstract"] = "current revision"
    dossier.save()
    assert SourceSnapshot.objects.filter(dossier=dossier).count() == 3
    call_command(
        "compact_research_sources", dossier=str(dossier.pk), prune_unreferenced=True, offline=True
    )
    assert SourceSnapshot.objects.filter(dossier=dossier).count() == 2
    assert not SourceSnapshot.objects.filter(dossier=dossier, digest=abandoned).exists()
    loaded = Dossier.objects.get(pk=dossier.pk)
    assert loaded.versions[0]["papers"] == [PAPER]
    assert loaded.papers[0]["abstract"] == "current revision"


def test_pruning_requires_explicit_offline_confirmation():
    dossier = make_dossier()
    with pytest.raises(CommandError, match="stop web and research workers"):
        call_command("compact_research_sources", dossier=str(dossier.pk), prune_unreferenced=True)
    assert SourceSnapshot.objects.filter(dossier=dossier).count() == 1
