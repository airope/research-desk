"""Explicit worker/maintenance writes. Web retrieval never calls this module."""

from django.conf import settings
from elastic_transport import TransportError
from elasticsearch import ApiError
from elasticsearch.helpers import BulkIndexError, bulk

from .search_index import INDEX, MAPPINGS, SearchUnavailable, connection, documents


def purge_scope(scope, *, keep_ids=(), client=None):
    """Remove obsolete documents, or the entire deleted dossier's search scope."""
    owned = client is None
    client = client or connection(write=True)
    query = {"bool": {"filter": [{"term": {"scope": scope}}]}}
    if keep_ids:
        query["bool"]["must_not"] = [{"ids": {"values": list(keep_ids)}}]
    try:
        response = client.delete_by_query(
            index=INDEX, query=query, refresh=True, conflicts="abort", timeout="10s"
        )
        if response.get("timed_out") or response.get("failures"):
            raise SearchUnavailable("Passage index cleanup did not complete; retry maintenance.")
    except ApiError as exc:
        if exc.status_code != 404:
            raise SearchUnavailable("Passage index cleanup failed; retry maintenance.") from exc
    except TransportError as exc:
        raise SearchUnavailable("Passage index cleanup failed; retry maintenance.") from exc
    finally:
        if owned:
            client.close()


def index_sources(papers, scope, *, client=None):
    """Publish all dossier sources, then purge old revisions only after successful bulk.

    Caller must serialize writers per dossier (worker run fencing / row lock).
    Unselected papers remain indexed so changing selection requires no network writes.
    """
    if settings.RESEARCH_SEARCH_BACKEND != "elasticsearch":
        return
    if not scope:
        raise SearchUnavailable("A dossier scope is required for indexing.")
    _, rows = documents(papers, scope)
    owned = client is None
    client = client or connection(write=True)
    try:
        try:
            client.indices.create(
                index=INDEX,
                mappings=MAPPINGS,
                settings={"number_of_shards": 1, "number_of_replicas": 0},
            )
        except ApiError as exc:
            if exc.error != "resource_already_exists_exception":
                raise
        ready = (
            client.count(
                index=INDEX,
                query={
                    "bool": {
                        "filter": [{"term": {"scope": scope}}, {"ids": {"values": list(rows)}}]
                    }
                },
            )
            if rows
            else {"count": 0}
        )
        if ready.get("_shards", {}).get("failed", 0):
            raise SearchUnavailable("Passage index readiness check failed.")
        if rows and ready["count"] != len(rows):
            bulk(
                client,
                ({"_index": INDEX, "_id": key, "_source": row} for key, row in rows.items()),
                refresh="wait_for",
                chunk_size=250,
            )
        purge_scope(scope, keep_ids=rows, client=client)
    except (ApiError, TransportError, BulkIndexError, ValueError) as exc:
        raise SearchUnavailable(
            "Passage indexing failed. Existing sources are retained; retry the job."
        ) from exc
    finally:
        if owned:
            client.close()
