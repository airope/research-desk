"""Full-text boundaries are enforced before untrusted PDFs reach the parser."""

import hashlib
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from research import fulltext, pdf_extract


@pytest.fixture(autouse=True)
def fake_repository_clock(monkeypatch, tmp_path):
    clock = SimpleNamespace(now=0.0, waits=[])

    def sleep(seconds):
        clock.waits.append(seconds)
        clock.now += seconds

    monkeypatch.setattr(fulltext, "time", SimpleNamespace(monotonic=lambda: clock.now, sleep=sleep))
    monkeypatch.setattr(fulltext, "ARXIV_STATE", tmp_path / "arxiv.lock")
    return clock


URL = "https://arxiv.org/pdf/2401.12345"
PDF = b"%PDF-1.4\nexample"


@pytest.mark.parametrize(
    "url",
    [
        "http://arxiv.org/pdf/2401.12345",
        "https://arxiv.org.evil.test/pdf/2401.12345",
        "https://127.0.0.1/pdf/2401.12345",
        "https://arxiv.org:443/pdf/2401.12345",
        "https://user@arxiv.org/pdf/2401.12345",
        "https://arxiv.org/pdf/../../private",
        URL + "?url=http://localhost",
        URL + "#fragment",
        "https://inspirehep.net/api/literature/1",
    ],
)
def test_invalid_urls_do_not_make_requests(url):
    client = Mock()
    assert fulltext.fetch_document({"fulltext_url": url}, client=client)["status"] == "unavailable"
    client.stream.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        URL,
        URL + "v2.pdf",
        "https://arxiv.org/pdf/hep-ph/9901234",
        "https://inspirehep.net/files/" + "a" * 32,
    ],
)
def test_supported_urls(url):
    assert fulltext.safe_url(url)


def test_redirect_rejects_arbitrary_host_before_request():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = fulltext.fetch_document({"fulltext_url": URL}, client=client)
    assert result["status"] == "failed"
    assert calls == [URL]


def test_too_many_redirects_stop_at_four_requests():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": URL})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = fulltext.fetch_document({"fulltext_url": URL}, client=client)
    assert result["status"] == "failed"
    assert len(calls) == 4


@pytest.mark.parametrize("headers,body", [({"content-length": "99999999"}, PDF), ({}, PDF * 10)])
def test_size_cap_prevents_parsing(monkeypatch, headers, body):
    monkeypatch.setattr(fulltext, "MAX_BYTES", len(PDF) + 1)
    extract = Mock()
    monkeypatch.setattr(fulltext, "_extract", extract)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, headers=headers, content=body)
        )
    ) as client:
        result = fulltext.fetch_document({"fulltext_url": URL}, client=client)
    assert result["status"] == "failed"
    extract.assert_not_called()


def test_success_retains_checksum_physical_pages_and_truncation(monkeypatch):
    extracted = {
        "pages": [{"page": 1, "text": "Measured tracking results."}],
        "total_pages": 60,
        "truncated": True,
    }
    monkeypatch.setattr(fulltext, "_extract", lambda data: extracted)
    with httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, content=PDF))
    ) as client:
        result = fulltext.fetch_document({"fulltext_url": URL}, client=client)
    assert result["status"] == "available"
    assert result["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert result["retrieved_at"]
    assert result["pages"] == extracted["pages"]
    assert result["total_pages"] == 60 and result["truncated"]
    assert result["page_numbering"] == "physical_pdf"


def test_scanned_pdf_never_claims_text_available(monkeypatch):
    monkeypatch.setattr(
        fulltext, "_extract", lambda data: {"pages": [{"page": 1, "text": ""}], "total_pages": 1}
    )
    with httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, content=PDF))
    ) as client:
        result = fulltext.fetch_document({"fulltext_url": URL}, client=client)
    assert result["status"] == "unavailable"
    assert "OCR" in result["error"]


def test_page_limits_and_whitespace_keep_physical_numbering(monkeypatch):
    monkeypatch.setattr(pdf_extract, "MAX_PAGES", 3)
    monkeypatch.setattr(pdf_extract, "MAX_PAGE_CHARS", 12)
    monkeypatch.setattr(pdf_extract, "MAX_TOTAL_CHARS", 20)
    reader = SimpleNamespace(
        pages=[
            Mock(extract_text=Mock(return_value=text))
            for text in ["", "one\n two\tthree four", "many more words", "ignored"]
        ]
    )
    result = pdf_extract.extract_pages(reader)
    assert result["pages"][0] == {"page": 1, "text": ""}
    assert result["pages"][1] == {"page": 2, "text": "one two thre"}
    assert result["pages"][2] == {"page": 3, "text": "many mor"}
    assert result["truncated"] and result["total_pages"] == 4


def test_parser_timeout_is_clean(monkeypatch):
    import subprocess

    def timeout(*args, **kwargs):
        assert kwargs["timeout"] == 30
        raise subprocess.TimeoutExpired(args[0], 30)

    monkeypatch.setattr(fulltext, "parser_command", lambda d: (["python", "-I"], "test"))
    monkeypatch.setattr(fulltext.subprocess, "run", timeout)
    with pytest.raises(fulltext.DocumentError, match="execution limits"):
        fulltext._extract(PDF)


def test_arxiv_redirect_and_fallback_requests_are_each_throttled(fake_repository_clock):
    observed = []
    second = "https://arxiv.org/pdf/2401.54321"

    def handler(request):
        observed.append((str(request.url), fake_repository_clock.now))
        if len(observed) == 1:
            return httpx.Response(302, headers={"location": URL + ".pdf"})
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = fulltext.fetch_document(
            {"fulltext_url": URL, "document_urls": [second]}, client=client
        )
    assert result["status"] == "failed"
    assert observed == [(URL, 0), (URL + ".pdf", 3), (second, 6)]
    assert fake_repository_clock.waits == [3, 3]


def test_inspire_requests_do_not_consume_arxiv_throttle(fake_repository_clock):
    inspire_url = "https://inspirehep.net/files/" + "b" * 32
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(404))) as client:
        fulltext.fetch_document({"fulltext_url": inspire_url}, client=client)
        fulltext.fetch_document({"fulltext_url": inspire_url}, client=client)
    assert fake_repository_clock.waits == []


def test_arxiv_throttle_is_shared_between_papers(fake_repository_clock):
    observed = []

    def handler(request):
        observed.append(fake_repository_clock.now)
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        fulltext.fetch_document({"fulltext_url": URL}, client=client)
        fulltext.fetch_document({"fulltext_url": URL}, client=client)
    assert observed == [0, 3]


def test_slow_stream_stops_at_total_deadline(monkeypatch, fake_repository_clock):
    class SlowStream(httpx.SyncByteStream):
        closed = False

        def __iter__(self):
            yield b"%PDF-"
            fake_repository_clock.now += fulltext.DOWNLOAD_SECONDS + 1
            yield b"slow content"

        def close(self):
            self.closed = True

    stream = SlowStream()
    parser = Mock()
    monkeypatch.setattr(fulltext, "_extract", parser)
    with httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, stream=stream))
    ) as client:
        result = fulltext.fetch_document({"fulltext_url": URL}, client=client)
    assert result["status"] == "failed"
    assert "deadline" in result["error"]
    assert stream.closed
    parser.assert_not_called()


def test_parser_receives_only_minimal_environment_and_temporary_cwd(monkeypatch):
    from pathlib import Path

    def run(command, **kwargs):
        assert set(kwargs["env"]) == {"LANG", "HOME", "TMPDIR"}
        assert kwargs["cwd"] == kwargs["env"]["HOME"]
        assert Path(kwargs["cwd"]).is_dir()
        assert "-I" in command
        return SimpleNamespace(returncode=0, stdout=b'{"pages": []}')

    monkeypatch.setattr(fulltext, "parser_command", lambda d: (["python", "-I"], "test"))
    monkeypatch.setenv("SECRET_KEY", "private-test-value")
    monkeypatch.setattr(fulltext.subprocess, "run", run)
    assert fulltext._extract(PDF)["isolation"] != "unknown"


def test_production_parser_fails_closed_without_sandbox(monkeypatch, settings):
    from research import pdf_sandbox

    monkeypatch.setattr(pdf_sandbox.sys, "platform", "unsupported")
    monkeypatch.setenv("RESEARCH_PDF_ALLOW_UNSANDBOXED_LOCAL", "1")
    settings.DEBUG = False
    with pytest.raises(pdf_sandbox.SandboxUnavailable):
        pdf_sandbox.parser_command("/tmp")
    settings.DEBUG = True
    assert pdf_sandbox.parser_command("/tmp")[1] == "explicit-local-fallback"
    monkeypatch.delenv("RESEARCH_PDF_ALLOW_UNSANDBOXED_LOCAL")
    with pytest.raises(pdf_sandbox.SandboxUnavailable):
        pdf_sandbox.parser_command("/tmp")


def test_repository_state_survives_independent_process_module(monkeypatch, fake_repository_clock):
    # Disk timestamp, rather than module state, coordinates independently loaded workers.
    fulltext.ARXIV_STATE.write_text("0.0")
    monkeypatch.setattr(fulltext, "_ARXIV_LOCK", __import__("threading").Lock())
    with fulltext._repository_slot(URL, 60):
        assert fake_repository_clock.now == 3
    assert float(fulltext.ARXIV_STATE.read_text()) == 3


def test_real_sandbox_denies_private_file_and_network(tmp_path):
    import os
    import subprocess

    from research.pdf_sandbox import parser_command, parser_environment

    if os.environ.get("RUN_PDF_SANDBOX_TEST") != "1":
        pytest.skip("Opt-in host integration: RUN_PDF_SANDBOX_TEST=1 (not a nested agent sandbox)")
    secret = tmp_path / "synthetic-private-file"
    secret.write_text("synthetic-only")
    command, isolation = parser_command(str(tmp_path))
    assert isolation != "explicit-local-fallback"
    command[-1:] = [
        "-c",
        f"""
import pathlib, socket
try:
    pathlib.Path({str(secret)!r}).read_text()
except (PermissionError, FileNotFoundError):
    pass
else:
    raise SystemExit("Private file was readable")
try:
    socket.create_connection(("127.0.0.1", 9), timeout=1)
except PermissionError:
    pass
except OSError as exc:
    # Linux network namespace has no route; macOS denies the socket operation.
    if {isolation!r} != "bubblewrap":
        raise
else:
    raise SystemExit("Network was accessible")
print("isolated")
""",
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        timeout=10,
        cwd=tmp_path,
        env=parser_environment(str(tmp_path)),
    )
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout == b"isolated\n"


@pytest.mark.parametrize("phase", ["body", "headers"])
def test_host_streaming_deadline_interrupts_continuous_slow_bytes(monkeypatch, phase):
    import os
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    if os.environ.get("RUN_PDF_SANDBOX_TEST") != "1":
        pytest.skip("Opt-in host integration requires loopback server permission")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if phase == "headers":
                try:
                    for byte in b"HTTP/1.1 200 OK\r\nContent-Length: 10000\r\n\r\n":
                        self.connection.sendall(bytes([byte]))
                        time.sleep(0.04)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
            self.send_response(200)
            self.send_header("Content-Length", "10000")
            self.end_headers()
            try:
                self.wfile.write(b"%PDF-")
                self.wfile.flush()
                for _ in range(100):
                    time.sleep(0.04)
                    self.wfile.write(b"x")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(fulltext, "time", time)
    monkeypatch.setattr(fulltext, "safe_url", lambda url: True)
    start = time.monotonic()
    try:
        with httpx.Client(trust_env=False) as client:
            with pytest.raises((fulltext.DocumentError, httpx.HTTPError)):
                fulltext._download(f"http://127.0.0.1:{server.server_port}/", client, start + 0.2)
        assert time.monotonic() - start < 0.8
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)
