from types import SimpleNamespace

import httpx
import pytest

from srr import http_deadline


@pytest.mark.parametrize("source", ["research", "catalogue", "metadata"])
def test_inspire_slow_body_deadline_applies_before_json_parsing(monkeypatch, source):
    clock = SimpleNamespace(now=0)
    monkeypatch.setattr(http_deadline, "time", SimpleNamespace(monotonic=lambda: clock.now))

    class SlowStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b'{"hits":'
            clock.now = 31
            yield b'{"hits": []}}'

    with httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, stream=SlowStream()))
    ) as client:
        if source == "research":
            from research.inspire import SearchError, search

            with pytest.raises(SearchError, match="request limits"):
                search("higgs", client=client)
        elif source == "metadata":
            from records.connectors import ConnectorError, MetadataClient

            with pytest.raises(ConnectorError, match="connection failed"):
                MetadataClient(client=client, attempts=1).get("https://api.openalex.org/works", {})
        else:
            from catalogues.acquisition import AcquisitionError, search_inspire

            with pytest.raises(AcquisitionError, match="request limits"):
                search_inspire({"collaboration": "ATLAS", "limit": 1}, client=client)
