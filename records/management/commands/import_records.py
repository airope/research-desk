from django.core.management.base import BaseCommand

from records.ingestion import create_import, process_run


class Command(BaseCommand):
    help = "Import a bounded local fixture or provider query."

    def add_arguments(self, parser):
        parser.add_argument("provider", choices=["crossref", "openalex"])
        parser.add_argument("--fixture", choices=["demo", "synthetic", "corpus"])
        parser.add_argument("--query")
        parser.add_argument("--max-records", type=int, default=100)
        parser.add_argument("--page-size", type=int, default=20)
        parser.add_argument("--queue", action="store_true")

    def handle(self, *args, **options):
        profile = {
            key: options[key]
            for key in ("fixture", "query", "max_records", "page_size")
            if options.get(key) is not None
        }
        run = create_import(options["provider"], profile)
        if not options["queue"]:
            run = process_run(run.pk)
        self.stdout.write(f"{run.pk} {run.status} {run.counters}")
