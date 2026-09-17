import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from research.heartbeat import lease
from research.jobs import claim, execute


class Command(BaseCommand):
    help = "Run the research queue using the explicitly configured LLM provider."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        self.stdout.write("Research worker ready.")
        while True:
            close_old_connections()
            dossier = claim()
            if dossier:
                with lease(dossier):
                    execute(dossier)
            if options["once"]:
                return
            if not dossier:
                time.sleep(1)
