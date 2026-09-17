"""Opt-in Elasticsearch contract; shared-index mode only touches random test scopes."""

import copy
import os
import uuid
from unittest.mock import patch

import pytest
from elasticsearch import Elasticsearch

from research import indexing, search_index

URL = os.getenv("RESEARCH_TEST_ELASTICSEARCH_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="Disposable Elasticsearch URL not configured")


def paper(identity, text):
    return {
        "id": identity,
        "title": "FPGA latency study",
        "abstract": "Latency overview",
        "document": {"status": "available", "pages": [{"page": 1, "text": text}]},
    }


def test_real_bulk_msearch_revisions_subset_and_scope_purge(settings, monkeypatch):
    shared_index = os.getenv("RESEARCH_TEST_SHARED_INDEX", "")
    index = shared_index or "test-research-" + uuid.uuid4().hex
    scope_a = "audit-test-a:" + uuid.uuid4().hex
    scope_b = "audit-test-b:" + uuid.uuid4().hex
    monkeypatch.setattr(indexing, "INDEX", index)
    monkeypatch.setattr(search_index, "INDEX", index)
    settings.RESEARCH_SEARCH_BACKEND = "elasticsearch"
    first = paper("1", "The FPGA pipeline latency is 10 microseconds.")
    second = paper("2", "The FPGA pipeline latency is 20 microseconds.")
    options = {"request_timeout": 10, "max_retries": 0}
    if os.getenv("RESEARCH_TEST_ELASTICSEARCH_API_KEY"):
        options["api_key"] = os.environ["RESEARCH_TEST_ELASTICSEARCH_API_KEY"]
    client = Elasticsearch(URL, **options)

    def scoped_count():
        return client.count(index=index, query={"terms": {"scope": [scope_a, scope_b]}})["count"]

    def index_total():
        return client.indices.stats(index=index)["indices"][index]["primaries"]["indexing"][
            "index_total"
        ]

    try:
        indexing.index_sources([first], scope_a, client=client)
        _, original = search_index.documents([first], scope_a)
        indexing.index_sources([first, second], scope_a, client=client)
        _, expanded = search_index.documents([first, second], scope_a)
        assert set(original).issubset(expanded)
        assert scoped_count() == len(expanded)
        # Subset retrieval must use the same immutable paper revision; it cannot index.
        before = None if shared_index else index_total()
        with patch("research.indexing.bulk", wraps=indexing.bulk) as bulk_spy:
            matches = search_index.ranked_passages(
                "pipeline latency", [first], scope_a, client=client
            )
            bulk_spy.assert_not_called()
        assert matches["1"][0][1] == 1
        assert "10 microseconds" in matches["1"][0][3]
        assert set(matches) == {"1"}
        if not shared_index:
            assert index_total() == before
        with patch("research.indexing.bulk", wraps=indexing.bulk) as bulk_spy:
            indexing.index_sources([first, second], scope_a, client=client)
            bulk_spy.assert_not_called()
        if not shared_index:
            assert index_total() == before
        # A different owner/scope survives another scope's replacement and deletion.
        indexing.index_sources([first], scope_b, client=client)
        revised = copy.deepcopy(first)
        revised["document"]["pages"][0]["text"] = "The revised pipeline latency is 5 microseconds."
        indexing.index_sources([revised], scope_a, client=client)
        _, active_a = search_index.documents([revised], scope_a)
        _, active_b = search_index.documents([first], scope_b)
        assert scoped_count() == len(active_a) + len(active_b)
        with pytest.raises(search_index.SearchUnavailable, match="not ready"):
            search_index.ranked_passages("latency", [first], scope_a, client=client)
        indexing.purge_scope(scope_a, client=client)
        assert scoped_count() == len(active_b)
        assert search_index.ranked_passages("latency", [first], scope_b, client=client)["1"]
    finally:
        try:
            if shared_index:
                # Attempt both cleanups even when the first fails; never delete the shared index.
                try:
                    indexing.purge_scope(scope_a, client=client)
                finally:
                    indexing.purge_scope(scope_b, client=client)
            else:
                client.indices.delete(index=index, ignore_unavailable=True)
        finally:
            client.close()
