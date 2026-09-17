"""Best-effort post-commit deletion; orphan maintenance retries unavailable search."""

import logging

from django.conf import settings
from django.db import transaction

from .indexing import purge_scope
from .search_index import SearchUnavailable

logger = logging.getLogger(__name__)


def delete_passage_scope(sender, instance, using, **kwargs):
    if settings.RESEARCH_SEARCH_BACKEND != "elasticsearch":
        return
    scope = f"{instance.owner_id}:{instance.pk}"

    def cleanup():
        try:
            purge_scope(scope)
        except SearchUnavailable:
            logger.warning("Passage index deletion deferred; run reindex_research --purge-orphans.")

    transaction.on_commit(cleanup, using=using)
