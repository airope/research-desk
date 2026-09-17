import copy
from unittest.mock import MagicMock, patch

import pytest

from research import search_index
from research.retrieval import select_evidence
from tests.test_research_evidence import PAPER


def test_document_ids_are_idempotent_and_scope_and_content_sensitive():
    corpus, rows = search_index.documents([PAPER], "owner:dossier")
    assert (corpus, rows) == search_index.documents([PAPER], "owner:dossier")
    assert not rows.keys() & search_index.documents([PAPER], "other:dossier")[1].keys()
    changed = copy.deepcopy(PAPER)
    changed["document"]["pages"][1]["text"] += " Revised evidence."
    assert corpus != search_index.documents([changed], "owner:dossier")[0]


def test_search_is_read_only_and_filters_scope_revision_paper_page():
    corpus, rows = search_index.documents([PAPER], "owner:dossier")
    key = next(key for key, row in rows.items() if row["page"] == 2)
    client = MagicMock()
    client.count.return_value = {"count": len(rows)}
    client.msearch.return_value = {"responses": [{"hits": {"hits": [{"_id": key, "_score": 9.1}]}}]}
    result = search_index.ranked_passages("latency", [PAPER], "owner:dossier", client=client)
    assert result["101"][0] == (9.1, 2, 0, rows[key]["text"])
    query = client.msearch.call_args.kwargs["searches"][1]["query"]["bool"]
    assert {"term": {"scope": "owner:dossier"}} in query["filter"]
    assert {"terms": {"corpus": [rows[key]["corpus"]]}} in query["filter"]
    assert {"term": {"paper_id": "101"}} in query["filter"]
    assert {"range": {"page": {"gt": 0}}} in query["filter"]
    client.indices.create.assert_not_called()
    client.bulk.assert_not_called()
    client.delete_by_query.assert_not_called()


@pytest.mark.parametrize(
    "response",
    [
        {"hits": {"hits": [{"_id": "foreign", "_score": 1}]}},
        {"timed_out": True, "hits": {"hits": []}},
        {"_shards": {"failed": 1}, "hits": {"hits": []}},
    ],
)
def test_stale_foreign_and_incomplete_results_are_rejected(response):
    client = MagicMock()
    client.count.return_value = {"count": len(search_index.documents([PAPER], "scope")[1])}
    client.msearch.return_value = {"responses": [response]}
    with pytest.raises(search_index.SearchUnavailable):
        search_index.ranked_passages("latency", [PAPER], "scope", client=client)


def test_es_failure_has_no_substitute_ranking(settings):
    settings.RESEARCH_SEARCH_BACKEND = "elasticsearch"
    with patch(
        "research.search_index.ranked_passages",
        side_effect=search_index.SearchUnavailable("offline"),
    ):
        result = select_evidence("latency", [{**PAPER, "_search_scope": "scope"}])
    assert result[0]["_retrieval"] == {"engine": "unavailable", "warning": "offline"}
    assert all(p["page"] == 0 for p in result[0]["_evidence_passages"])


def test_es_rank_order_and_budgets_are_respected(settings):
    settings.RESEARCH_SEARCH_BACKEND = "elasticsearch"
    text = PAPER["document"]["pages"][1]["text"]
    with patch("research.search_index.ranked_passages", return_value={"101": [(12, 2, 0, text)]}):
        result = select_evidence("latency", [{**PAPER, "_search_scope": "scope"}])
    assert result[0]["_retrieval"]["engine"] == "elasticsearch-bm25"
    assert result[0]["_evidence_passages"][1]["score"] == 12
    assert sum(len(p["text"]) for p in result[0]["_evidence_passages"]) <= 4000


def test_missing_scope_never_indexes_sources(settings):
    settings.RESEARCH_SEARCH_BACKEND = "elasticsearch"
    with patch("research.search_index.connection") as connection:
        result = select_evidence("latency", [PAPER])
    connection.assert_not_called()
    assert result[0]["_retrieval"]["warning"]


@pytest.mark.django_db
def test_passage_search_ui_is_owner_scoped_and_shows_backend(client, monkeypatch):
    from django.contrib.auth.models import User
    from django.urls import reverse

    from research.models import Dossier

    owner = User.objects.create_user("search-owner")
    outsider = User.objects.create_user("search-other")
    dossier = Dossier.objects.create(
        owner=owner, question="Tracking latency", status="ready", papers=[PAPER], selected=["101"]
    )
    monkeypatch.setattr("research.ai.availability", lambda: (False, "Disabled"))
    client.force_login(outsider)
    with patch("research.passage_search.search") as search:
        response = client.get(
            reverse("research:detail", args=[dossier.pk]), {"tab": "passages", "q": "latency"}
        )
    assert response.status_code == 404
    search.assert_not_called()
    client.force_login(owner)
    response = client.get(
        reverse("research:detail", args=[dossier.pk]),
        {"tab": "passages", "q": "latency", "paper": "101", "page": 2},
    )
    assert response.status_code == 200
    assert b"Local keyword ranking" in response.content
    assert b"PDF page 2" in response.content
    assert b"<mark>" in response.content


def test_adding_another_paper_preserves_existing_ids():
    other = {**PAPER, "id": "202"}
    _, before = search_index.documents([PAPER], "scope")
    _, after = search_index.documents([PAPER, other], "scope")
    assert before.items() <= after.items()


def test_incomplete_index_does_not_search():
    client = MagicMock()
    client.count.return_value = {"count": 0}
    with pytest.raises(search_index.SearchUnavailable, match="not ready"):
        search_index.ranked_passages("latency", [PAPER], "scope", client=client)
    client.msearch.assert_not_called()


def test_worker_bulk_failure_never_purges_old_sources(settings):
    from elasticsearch.helpers import BulkIndexError

    from research.indexing import index_sources

    settings.RESEARCH_SEARCH_BACKEND = "elasticsearch"
    client = MagicMock()
    client.count.return_value = {"count": 0}
    with patch("research.indexing.bulk", side_effect=BulkIndexError("failed", [])):
        with pytest.raises(search_index.SearchUnavailable):
            index_sources([PAPER], "scope", client=client)
    client.delete_by_query.assert_not_called()


def test_worker_replaces_only_its_own_obsolete_documents(settings):
    from research.indexing import index_sources

    settings.RESEARCH_SEARCH_BACKEND = "elasticsearch"
    client = MagicMock()
    client.count.return_value = {"count": 0}
    client.delete_by_query.return_value = {"deleted": 3, "failures": []}
    with patch("research.indexing.bulk") as write:
        index_sources([PAPER], "scope", client=client)
    assert write.call_args.kwargs["refresh"] == "wait_for"
    query = client.delete_by_query.call_args.kwargs["query"]["bool"]
    assert query["filter"] == [{"term": {"scope": "scope"}}]
    assert set(query["must_not"][0]["ids"]["values"]) == set(
        search_index.documents([PAPER], "scope")[1]
    )


def test_delete_dossier_scope_purges_all_its_documents():
    from research.indexing import purge_scope

    client = MagicMock()
    client.delete_by_query.return_value = {"deleted": 3}
    purge_scope("scope", client=client)
    assert client.delete_by_query.call_args.kwargs["query"] == {
        "bool": {"filter": [{"term": {"scope": "scope"}}]}
    }


def test_unchanged_worker_index_skips_bulk(settings):
    from research.indexing import index_sources

    settings.RESEARCH_SEARCH_BACKEND = "elasticsearch"
    client = MagicMock()
    client.count.return_value = {"count": len(search_index.documents([PAPER], "scope")[1])}
    client.delete_by_query.return_value = {"deleted": 0}
    with patch("research.indexing.bulk") as write:
        index_sources([PAPER], "scope", client=client)
    write.assert_not_called()


@pytest.mark.django_db
def test_delete_signal_runs_after_commit_and_cascade(
    client, settings, django_capture_on_commit_callbacks
):
    from django.contrib.auth.models import User

    from research.models import Dossier

    settings.RESEARCH_SEARCH_BACKEND = "elasticsearch"
    owner = User.objects.create_user("index-delete-owner")
    dossier = Dossier.objects.create(owner=owner, question="test")
    scope = f"{owner.pk}:{dossier.pk}"
    with patch("research.signals.purge_scope") as purge:
        with django_capture_on_commit_callbacks(execute=True):
            owner.delete()
            purge.assert_not_called()
        purge.assert_called_once_with(scope)


def test_pdf_only_unavailable_result_keeps_warning(settings):
    settings.RESEARCH_SEARCH_BACKEND = "elasticsearch"
    with patch(
        "research.search_index.ranked_passages",
        side_effect=search_index.SearchUnavailable("not ready"),
    ):
        result = select_evidence("latency", [{**PAPER, "abstract": "", "_search_scope": "scope"}])
    assert result[0]["_retrieval"] == {"engine": "unavailable", "warning": "not ready"}
    assert result[0]["_evidence_passages"] == []
