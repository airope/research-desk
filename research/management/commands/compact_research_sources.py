from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from research.models import Dossier, SourceSnapshot
from research.source_storage import SOURCE_FIELDS, references


class Command(BaseCommand):
    help = "Deduplicate existing source texts without changing report content (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--dossier", help="Limit compaction to one dossier UUID")
        parser.add_argument(
            "--prune-unreferenced",
            action="store_true",
            help="Delete snapshots no longer referenced by current sources or any retained report version",
        )

        parser.add_argument(
            "--offline",
            action="store_true",
            help="Confirm web and research workers are stopped before pruning snapshots",
        )

    def handle(self, *args, **options):
        if options["prune_unreferenced"] and not options["offline"]:
            raise CommandError(
                "Pruning requires --offline: stop web and research workers first to protect active readers."
            )
        query = Dossier.objects.order_by("pk")
        if options["dossier"]:
            query = query.filter(pk=options["dossier"])
        count = 0
        removed = 0
        for pk in query.values_list("pk", flat=True).iterator(chunk_size=100):
            with transaction.atomic():
                dossier = Dossier.objects.select_for_update().get(pk=pk)
                before = {name: getattr(dossier, name) for name in SOURCE_FIELDS}
                dossier.save(update_fields=SOURCE_FIELDS)
                verified = Dossier.objects.get(pk=pk)
                if any(getattr(verified, name) != value for name, value in before.items()):
                    raise RuntimeError(f"Source round-trip failed for dossier {pk}")
                if options["prune_unreferenced"]:
                    raw = Dossier.objects.filter(pk=pk).values(*SOURCE_FIELDS).get()
                    active = set()
                    for value in raw.values():
                        active.update(references(value))
                    deleted, _ = (
                        SourceSnapshot.objects.filter(dossier_id=pk)
                        .exclude(digest__in=active)
                        .delete()
                    )
                    removed += deleted
            count += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Compacted and verified {count} dossier(s); pruned {removed} unreferenced snapshot(s)."
            )
        )
