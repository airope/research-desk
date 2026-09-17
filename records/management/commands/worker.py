import os
import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from records.ingestion import SimulatedCrash, process_run
from records.models import ImportRun


class Command(BaseCommand):
    help = "Claim queued imports or reclaim expired worker leases."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--run-id")
        parser.add_argument("--crash-after", type=int)
        parser.add_argument(
            "--hard-crash",
            action="store_true",
            help="Exit process immediately with status 137 after the injected persistence crash.",
        )
        parser.add_argument(
            "--expire-lease",
            action="store_true",
            help="Controlled demo only: expire this run lease after injected crash.",
        )

    def handle(self, *args, **options):
        while True:
            try:
                run = process_run(options["run_id"], crash_after=options["crash_after"])
                if run:
                    self.stdout.write(f"{run.pk} {run.status} {run.counters}")
            except SimulatedCrash as exc:
                if options["expire_lease"] and options["run_id"]:
                    ImportRun.objects.filter(pk=options["run_id"], status="running").update(
                        lease_expires_at=timezone.now()
                    )
                self.stderr.write(str(exc))
                if options["hard_crash"]:
                    os._exit(137)
                return
            if options["once"]:
                return
            if not run:
                time.sleep(2)
