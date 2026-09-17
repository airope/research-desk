"""Read-only Elasticsearch retrieval, scoped to immutable source revisions."""

import hashlib
import json

from django.conf import settings
from elastic_transport import TransportError
from elasticsearch import ApiError, Elasticsearch

INDEX = "research-passages-v1"
MAPPINGS = {
    "dynamic": "strict",
    "properties": {
        "scope": {"type": "keyword"},
        "corpus": {"type": "keyword"},  # Per-paper revision; compatible with the existing mapping.
        "paper_id": {"type": "keyword"},
        "page": {"type": "integer"},
        "position": {"type": "integer"},
        "title": {"type": "text", "analyzer": "english"},
        "text": {"type": "text", "analyzer": "english"},
    },
}


class SearchUnavailable(Exception):
    pass


def connection(*, write=False):
    options = {"request_timeout": 10, "max_retries": 0}
    read_key = getattr(settings, "RESEARCH_ELASTICSEARCH_READ_API_KEY", "")
    key = (
        settings.RESEARCH_ELASTICSEARCH_API_KEY
        if write
        else read_key or settings.RESEARCH_ELASTICSEARCH_API_KEY
    )
    if key:
        options["api_key"] = key
    if settings.RESEARCH_ELASTICSEARCH_CA_CERTS:
        options["ca_certs"] = settings.RESEARCH_ELASTICSEARCH_CA_CERTS
    return Elasticsearch(settings.RESEARCH_ELASTICSEARCH_URL, **options)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def documents(papers, scope):
    from .retrieval import _chunks, source_passages

    result = {}
    for paper in papers[:20]:
        rows = []
        for passage in source_passages(paper):
            for position, chunk in enumerate(_chunks(passage["text"])):
                rows.append(
                    {
                        "scope": scope,
                        "paper_id": paper["id"],
                        "title": paper["title"],
                        "page": passage["page"],
                        "position": position,
                        "text": chunk,
                    }
                )
        revision = digest(rows)
        for row in rows:
            row["corpus"] = revision
            result[digest(row)] = row
    return digest(sorted(result)), result


def _complete(response):
    if (
        response.get("error")
        or response.get("timed_out")
        or response.get("_shards", {}).get("failed", 0)
    ):
        raise SearchUnavailable("Elasticsearch returned incomplete results.")


def ranked_passages(question, papers, scope, *, client=None):
    """Never create or write an index during retrieval; reject incomplete snapshots."""
    if not scope:
        raise SearchUnavailable("A dossier scope is required for Elasticsearch retrieval.")
    _, rows = documents(papers, scope)
    if not rows:
        return {}
    owned = client is None
    client = client or connection()
    try:
        ready = client.count(
            index=INDEX,
            query={
                "bool": {"filter": [{"term": {"scope": scope}}, {"ids": {"values": list(rows)}}]}
            },
        )
        _complete(ready)
        if ready["count"] != len(rows):
            raise SearchUnavailable(
                "Passage index is not ready for these sources. Run reindex_research or retry the research job."
            )
        searches, sources = [], []
        for paper in papers[:20]:
            revisions = {row["corpus"] for row in rows.values() if row["paper_id"] == paper["id"]}
            if not revisions:
                continue
            sources.append(paper)
            searches.extend(
                [
                    {"index": INDEX},
                    {
                        "query": {
                            "bool": {
                                "filter": [
                                    {"term": {"scope": scope}},
                                    {"terms": {"corpus": sorted(revisions)}},
                                    {"term": {"paper_id": paper["id"]}},
                                    {"range": {"page": {"gt": 0}}},
                                ],
                                "must": [
                                    {
                                        "multi_match": {
                                            "query": question[:4000],
                                            "fields": ["text", "title^0.2"],
                                            "type": "best_fields",
                                        }
                                    }
                                ],
                            }
                        },
                        "size": 5,
                        "_source": False,
                        "sort": ["_score", {"page": "asc"}, {"position": "asc"}],
                    },
                ]
            )
        responses = client.msearch(searches=searches)["responses"]
        if len(responses) != len(sources):
            raise SearchUnavailable("Elasticsearch returned incomplete results.")
        ranked = {}
        for paper, response in zip(sources, responses, strict=True):
            _complete(response)
            values = []
            for hit in response["hits"]["hits"]:
                row = rows.get(hit["_id"])
                if not row or row["paper_id"] != paper["id"] or row["page"] <= 0:
                    raise SearchUnavailable(
                        "Search results did not match the current source snapshot."
                    )
                values.append((float(hit["_score"]), row["page"], row["position"], row["text"]))
            ranked[paper["id"]] = values
        return ranked
    except (ApiError, TransportError, ValueError, KeyError) as exc:
        raise SearchUnavailable(
            "Elasticsearch is unavailable. Passage search has not used a substitute ranking."
        ) from exc
    finally:
        if owned:
            client.close()
