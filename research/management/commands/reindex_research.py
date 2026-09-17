"""Rebuild dossier passages, or remove scopes whose dossier no longer exists."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from elastic_transport import TransportError
from elasticsearch import ApiError

from research.indexing import index_sources, purge_scope
from research.models import Dossier
from research.search_index import INDEX, SearchUnavailable, connection


class Command(BaseCommand):
    help = "Rebuild search passages (--dossier UUID optional) or --purge-orphans."

    def add_arguments(self, parser):
        parser.add_argument("--dossier")
        parser.add_argument("--purge-orphans", action="store_true")

    def handle(self, *args, **options):
        if settings.RESEARCH_SEARCH_BACKEND != "elasticsearch":
            raise CommandError("Set RESEARCH_SEARCH_BACKEND=elasticsearch first.")
        try:
            if options["purge_orphans"]:
                self.purge_orphans()
                return
            dossiers = Dossier.objects.all()
            if options["dossier"]:
                dossiers = dossiers.filter(pk=options["dossier"])
                if not dossiers.exists():
                    raise CommandError("Dossier not found.")
            for pk in dossiers.values_list("pk", flat=True).iterator(chunk_size=100):
                with transaction.atomic():
                    dossier = Dossier.objects.select_for_update().get(pk=pk)
                    if dossier.status in {"running", "queued"}:
                        self.stdout.write(f"Skipped active dossier {pk}.")
                        continue
                    index_sources(dossier.papers, f"{dossier.owner_id}:{pk}")
                self.stdout.write(f"Indexed {pk}.")
        except SearchUnavailable as exc:
            raise CommandError(str(exc)) from exc
        except (ApiError, TransportError) as exc:
            if isinstance(exc, ApiError) and exc.status_code == 404 and options["purge_orphans"]:
                self.stdout.write("No passage index exists; nothing to purge.")
                return
            raise CommandError(
                "Elasticsearch maintenance failed; verify access and retry."
            ) from exc

    def purge_orphans(self):
        with connection(write=True) as client:
            after = None
            while True:
                composite = {"size": 100, "sources": [{"scope": {"terms": {"field": "scope"}}}]}
                if after:
                    composite["after"] = after
                response = client.search(
                    index=INDEX, size=0, aggregations={"scopes": {"composite": composite}}
                )
                if response.get("timed_out") or response.get("_shards", {}).get("failed", 0):
                    raise SearchUnavailable("Scope inventory incomplete; retry maintenance.")
                groups = response["aggregations"]["scopes"]
                for bucket in groups["buckets"]:
                    scope = bucket["key"]["scope"]
                    try:
                        owner, pk = scope.split(":", 1)
                        exists = Dossier.objects.filter(pk=pk, owner_id=owner).exists()
                    except (ValueError, TypeError, ValidationError):
                        # Unknown namespaces must never be treated as owned dossiers.
                        continue
                    if not exists:
                        purge_scope(scope, client=client)
                        self.stdout.write(f"Purged {scope}.")
                after = groups.get("after_key")
                if not after or not groups["buckets"]:
                    return
