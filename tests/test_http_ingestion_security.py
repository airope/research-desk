"""Wire-level contracts: no content decoder may run on upstream ingestion."""

import gzip
import json

import httpx
import pytest

from catalogues.acquisition import AcquisitionError, search_inspire
from records.connectors import ConnectorError, MetadataClient
from research.fulltext import DocumentError, _download
from research.inspire import SearchError, search
from research.llm.config import ProviderError
from research.llm.transport import generate


class WireStream(httpx.SyncByteStream):
    def __init__(self, data):
        self.data = data
        self.read = False
        self.closed = False

    def __iter__(self):
        self.read = True
        yield self.data

    def close(self):
        self.closed = True


def invoke(path, client):
    if path == "metadata":
        return MetadataClient(client=client, attempts=1).get("https://api.crossref.org/works", {})
    if path == "pdf":
        return _download("https://inspirehep.net/files/" + "a" * 32, client)[0]
    if path == "research":
        return search("higgs", client=client)
    if path == "catalogue":
        return search_inspire({"collaboration": "ATLAS"}, client=client)["rows"]
    return generate("Question", {"type": "object"}, client=client)


@pytest.fixture(autouse=True)
def llm_configuration(settings):
    settings.LLM_PROVIDER = "openai"
    settings.LLM_API_KEY = "fixture-only"
    settings.LLM_PROVIDER_KEYS = {}
    settings.LLM_BASE_URL = ""
    settings.LLM_MODEL = ""
    settings.LLM_OUTPUT_MODE = ""


@pytest.mark.parametrize("path", ["pdf", "research", "catalogue", "llm", "metadata"])
@pytest.mark.parametrize("encoding", ["gzip", "deflate", "br", "identity, gzip", "unknown"])
@pytest.mark.parametrize("length", [None, "1"])
def test_encoded_response_rejected_before_decoder_or_body_read(monkeypatch, path, encoding, length):
    wire = WireStream(gzip.compress(b"x" * (16 * 1024 * 1024)))
    headers = {"Content-Encoding": encoding}
    if length is not None:
        headers["Content-Length"] = length
    response = httpx.Response(200, headers=headers, stream=wire)

    def forbidden_decoder(*args, **kwargs):
        pytest.fail("Upstream ingestion constructed a content decoder")

    monkeypatch.setattr(response, "_get_content_decoder", forbidden_decoder)
    seen = []

    def handler(request):
        seen.append(request.headers["accept-encoding"])
        return response

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(
            (httpx.HTTPError, SearchError, AcquisitionError, ProviderError, ConnectorError)
        ):
            invoke(path, client)
    assert seen == ["identity"]
    assert not wire.read
    assert wire.closed


@pytest.mark.parametrize("path", ["pdf", "research", "catalogue", "llm", "metadata"])
@pytest.mark.parametrize("encoding", [None, "identity"])
def test_unencoded_missing_length_stream_succeeds_without_decoder(monkeypatch, path, encoding):
    data = {
        "metadata": b"{}",
        "pdf": b"%PDF-1.7\nfixture",
        "research": b'{"hits":{"hits":[]}}',
        "catalogue": b'{"hits":{"hits":[]}}',
        "llm": json.dumps(
            {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
        ).encode(),
    }[path]
    wire = WireStream(data)
    response = httpx.Response(
        200, headers={"Content-Encoding": encoding} if encoding else {}, stream=wire
    )

    def forbidden_decoder(*args, **kwargs):
        pytest.fail("Identity ingestion must use raw bytes, not iter_bytes")

    monkeypatch.setattr(response, "_get_content_decoder", forbidden_decoder)
    with httpx.Client(transport=httpx.MockTransport(lambda request: response)) as client:
        result = invoke(path, client)
    assert result == {"pdf": data, "research": [], "catalogue": [], "llm": {}, "metadata": {}}[path]
    assert wire.closed


@pytest.mark.parametrize("path", ["pdf", "research", "catalogue", "llm", "metadata"])
@pytest.mark.parametrize("chunks", [[b"x" * 11], [b"x" * 6, b"x" * 5]])
def test_wire_budget_is_checked_before_buffer_allocation(monkeypatch, path, chunks):
    import importlib

    module_name, cap = {
        "metadata": ("records.connectors", "MAX_BYTES"),
        "pdf": ("research.fulltext", "MAX_BYTES"),
        "research": ("research.inspire", "MAX_BYTES"),
        "catalogue": ("catalogues.acquisition", "INSPIRE_MAX_BYTES"),
        "llm": ("research.llm.transport", "MAX_RESPONSE_BYTES"),
    }[path]
    module = importlib.import_module(module_name)
    monkeypatch.setattr(module, cap, 10, raising=False)

    class CheckedBuffer(bytearray):
        def extend(self, chunk):
            assert len(self) + len(chunk) <= 10, "Oversize wire bytes copied before cap check"
            super().extend(chunk)

    class Chunks(httpx.SyncByteStream):
        def __iter__(self):
            yield from chunks
            pytest.fail("Read beyond the budget violation")

    monkeypatch.setattr(module, "bytearray", CheckedBuffer, raising=False)
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=Chunks()))
    ) as client:
        with pytest.raises(
            (DocumentError, SearchError, AcquisitionError, ProviderError, ConnectorError)
        ):
            invoke(path, client)
