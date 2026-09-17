from datetime import datetime, timezone

import httpx
import pytest

from records.connectors import ConnectorError, MetadataClient, retry_delay, snapshot


def client_for(handler, sleeps=None):
    return MetadataClient(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=(sleeps if sleeps is not None else []).append,
        min_interval=0,
    )


def test_backoff_then_success():
    calls, sleeps = [], []

    def handler(request):
        calls.append(request)
        return (
            httpx.Response(429, headers={"Retry-After": "2"})
            if len(calls) == 1
            else httpx.Response(200, json={"ok": True})
        )

    assert client_for(handler, sleeps).get("https://api.crossref.org/works", {}) == {"ok": True}
    assert [value for value in sleeps if value] == [2]


@pytest.mark.parametrize("status", [401, 403, 400])
def test_fatal_response_not_retried(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status)

    with pytest.raises(ConnectorError) as caught:
        client_for(handler).get("https://api.openalex.org/works", {})
    assert not caught.value.retryable
    assert len(calls) == 1


@pytest.mark.parametrize("kind", ["timeout", "server"])
def test_transient_failures_are_bounded(kind):
    calls = []

    def handler(request):
        calls.append(request)
        if kind == "timeout":
            raise httpx.ReadTimeout("mock", request=request)
        return httpx.Response(503)

    with pytest.raises(ConnectorError):
        client_for(handler).get("https://api.crossref.org/works", {})
    assert len(calls) == 3


def test_retry_after_http_date_and_bound():
    assert (
        retry_delay("Wed, 01 Jan 2025 00:00:05 GMT", 0, datetime(2025, 1, 1, tzinfo=timezone.utc))
        == 5
    )
    assert retry_delay("999999", 0) == 999999
    assert retry_delay("-1", 0) == 0


def test_snapshot_strips_abstract_and_unneeded_fields():
    assert snapshot(
        "crossref",
        {"DOI": "10.1000/test", "title": ["Title"], "abstract": "copyright", "secret": "no"},
    ) == {"DOI": "10.1000/test", "title": ["Title"]}


def test_openalex_page_has_bounded_size_and_cursor():
    def handler(request):
        assert request.url.params["per_page"] == "3"
        assert request.url.params["cursor"] == "*"
        return httpx.Response(
            200,
            json={
                "results": [{"id": "https://openalex.org/W1", "title": "Example"}],
                "meta": {"next_cursor": "abc"},
            },
        )

    records, cursor, done = client_for(handler).page(
        "openalex", {"page_size": 20, "max_records": 3}, {}
    )
    assert len(records) == 1 and cursor == {"offset": 1, "token": "abc"} and not done


def test_empty_crossref_page_finishes():
    records, cursor, done = client_for(
        lambda _: httpx.Response(200, json={"message": {"items": [], "next-cursor": "next"}})
    ).page("crossref", {"page_size": 20, "max_records": 100}, {})
    assert records == [] and done and cursor["offset"] == 0


def test_long_retry_after_stops_without_early_retry():
    calls, sleeps = [], []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "120"})

    with pytest.raises(ConnectorError) as caught:
        client_for(handler, sleeps).get("https://api.crossref.org/works", {})
    assert len(calls) == 1 and sleeps == []
    assert caught.value.retry_after == 120


@pytest.mark.parametrize("raw", [{"authorships": [{"author": 123}]}, {"authorships": 4}])
def test_malformed_author_schema_is_explicit(raw):
    with pytest.raises(ValueError):
        snapshot("openalex", raw)


@pytest.mark.parametrize("metadata", [None, [], "bad"])
def test_openalex_invalid_meta_is_terminal_connector_error(metadata):
    client = client_for(lambda _: httpx.Response(200, json={"results": [], "meta": metadata}))
    with pytest.raises(ConnectorError) as caught:
        client.page("openalex", {"page_size": 20, "max_records": 100}, {})
    assert caught.value.code == "invalid_payload"
    assert caught.value.retryable is False


def test_two_day_retry_after_is_not_shortened():
    client = client_for(lambda _: httpx.Response(429, headers={"Retry-After": "172800"}))
    with pytest.raises(ConnectorError) as caught:
        client.get("https://api.openalex.org/works", {})
    assert caught.value.retry_after == 172800


@pytest.mark.parametrize(
    "value", ["Infinity", "NaN", "1e999", "9999999999999999999999999999999999999999999999999999999"]
)
def test_absurd_retry_after_is_terminal_diagnostic(value):
    with pytest.raises(ConnectorError) as caught:
        retry_delay(value, 0)
    assert caught.value.code == "invalid_retry_after"
    assert not caught.value.retryable
