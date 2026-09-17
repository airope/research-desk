from django.core.management.base import BaseCommand

from records.ingestion import create_import, process_run
from records.services import generate_candidates


class Command(BaseCommand):
    help = "Load committed metadata fixtures and generate review candidates offline."

    def handle(self, *args, **options):
        for provider in ("crossref", "openalex"):
            run = process_run(create_import(provider, {"fixture": "demo", "max_records": 100}).pk)
            self.stdout.write(f"{provider}: {run.status} {run.counters}")
        self.stdout.write(f"Candidates: {generate_candidates()}")
