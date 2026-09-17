from django.conf import settings
from django.core.management.base import BaseCommand

from research import ai
from research.llm.config import PROVIDERS


class Command(BaseCommand):
    help = (
        "List supported LLM providers and configuration readiness without sending a paid request."
    )

    def handle(self, *args, **options):
        for name, provider in PROVIDERS.items():
            self.stdout.write(f"{name}: {provider.model or '<set LLM_MODEL>'} — {provider.key_env}")
        available, message = ai.availability()
        self.stdout.write(f"Selected: {settings.LLM_PROVIDER}; configured: {available}. {message}")
