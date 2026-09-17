import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from records.evaluation import evaluate


class Command(BaseCommand):
    help = "Evaluate immutable benchmark fixtures using PostgreSQL retrieval; rollback all temporary writes."

    def add_arguments(self, parser):
        parser.add_argument("--dataset", default=str(settings.BASE_DIR / "data/benchmark.json"))
        parser.add_argument(
            "--output", default=str(settings.BASE_DIR / "data/benchmark-report.json")
        )
        parser.add_argument("--k", type=int, default=20)

    def handle(self, *args, **options):
        report = evaluate(options["dataset"], options["k"])
        Path(options["output"]).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        self.stdout.write(self.style.SUCCESS(f"Report: {options['output']}"))
