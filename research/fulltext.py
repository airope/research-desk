"""Bounded, read-only PDF acquisition from fixed scientific repositories."""

import fcntl
import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

from srr.http_deadline import bounded_stream, raw_chunks

from .pdf_sandbox import SandboxUnavailable, parser_command, parser_environment

_ARXIV_LOCK = threading.Lock()
ARXIV_STATE = Path(
    os.environ.get(
        "RESEARCH_ARXIV_STATE",
        tempfile.gettempdir() + "/research-arxiv-" + str(os.getuid()) + ".lock",
    )
)
DOWNLOAD_SECONDS = 60.0
ARXIV_INTERVAL = 3.0

MAX_BYTES = 15 * 1024 * 1024
ARXIV_PATH = re.compile(r"/pdf/(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?(?:\.pdf)?")
INSPIRE_PATH = re.compile(r"/files/[a-fA-F0-9]{16,128}")


class DocumentError(ValueError):
    pass


def safe_url(value):
    """Accept only document endpoints, including at every redirect hop."""
    if not isinstance(value, str) or len(value) > 300 or any(c.isspace() for c in value):
        return False
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or parsed.port is not None
            or parsed.query
            or parsed.fragment
        ):
            return False
        return bool(
            (parsed.netloc == "arxiv.org" and ARXIV_PATH.fullmatch(parsed.path))
            or (parsed.netloc == "inspirehep.net" and INSPIRE_PATH.fullmatch(parsed.path))
        )
    except ValueError:
        return False


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise DocumentError("The document exceeded its total download deadline.")
    return remaining


@contextmanager
def _repository_slot(url, deadline):
    """Coordinate workers on one host (shared lock volume required across containers)."""
    if urlsplit(url).hostname != "arxiv.org":
        yield
        return
    if not _ARXIV_LOCK.acquire(timeout=_remaining(deadline)):
        raise DocumentError("The document exceeded its total download deadline.")
    try:
        descriptor = os.open(ARXIV_STATE, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "r+") as state:
            while True:
                try:
                    fcntl.flock(state, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    time.sleep(min(0.1, _remaining(deadline)))
            try:
                previous = state.read().strip()
                elapsed = time.monotonic() - float(previous) if previous else ARXIV_INTERVAL
                # A reboot resets monotonic time even if a shared lock volume persists.
                delay = ARXIV_INTERVAL - elapsed if elapsed >= 0 else 0
                if delay > 0:
                    time.sleep(min(delay, _remaining(deadline)))
                _remaining(deadline)
                yield
            finally:
                state.seek(0)
                state.write(str(time.monotonic()))
                state.truncate()
                state.flush()
                fcntl.flock(state, fcntl.LOCK_UN)
    finally:
        _ARXIV_LOCK.release()


def _download(url, client, deadline=None):
    deadline = deadline or time.monotonic() + DOWNLOAD_SECONDS
    for hop in range(4):
        if not safe_url(url):
            raise DocumentError("The document address is not an allowed repository PDF endpoint.")
        with (
            _repository_slot(url, deadline),
            bounded_stream(
                client,
                "GET",
                url,
                seconds=_remaining(deadline),
                timeout=min(25, _remaining(deadline)),
                follow_redirects=False,
            ) as (response, check_deadline),
        ):
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location", "")
                if not location or hop == 3:
                    raise DocumentError("The document exceeded the redirect limit.")
                url = urljoin(url, location)
                continue
            if response.status_code != 200:
                raise DocumentError(f"Document retrieval returned HTTP {response.status_code}.")
            length = response.headers.get("content-length", "")
            if length.isdigit() and int(length) > MAX_BYTES:
                raise DocumentError("The document exceeds the 15 MB download limit.")
            data = bytearray()
            for chunk in raw_chunks(response):
                _remaining(deadline)
                check_deadline()
                if len(data) + len(chunk) > MAX_BYTES:
                    raise DocumentError("The document exceeds the 15 MB download limit.")
                data.extend(chunk)
            if not data.startswith(b"%PDF-"):
                raise DocumentError("The repository did not return a PDF document.")
            return bytes(data), url
    raise DocumentError("The document exceeded the redirect limit.")


def _extract(data):
    try:
        with tempfile.TemporaryDirectory(prefix="research-pdf-") as directory:
            command, isolation = parser_command(directory)
            result = subprocess.run(
                command,
                input=data,
                capture_output=True,
                timeout=30,
                check=False,
                cwd=directory,
                env=parser_environment(directory),
            )
    except SandboxUnavailable as exc:
        raise DocumentError(str(exc)) from exc
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise DocumentError("PDF text extraction exceeded its execution limits.") from exc
    if result.returncode:
        raise DocumentError("The PDF could not be read within the extraction limits.")
    try:
        parsed = json.loads(result.stdout)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("pages"), list):
            raise ValueError
        parsed["isolation"] = isolation
        return parsed
    except (ValueError, UnicodeDecodeError) as exc:
        raise DocumentError("PDF extraction returned an invalid result.") from exc


def fetch_document(paper, *, client=None):
    """Return private text evidence and provenance; never persist downloaded binaries.

    arXiv HTTP operations share a host-wide lock and total download deadline.
    A page number is the one-based physical PDF page, not a printed page label.
    """
    result = {
        "status": "unavailable",
        "pages": [],
        "sha256": "",
        "url": "",
        "error": "",
        "truncated": False,
        "total_pages": 0,
        "retrieved_at": "",
        "page_numbering": "physical_pdf",
    }
    candidates = [paper.get("fulltext_url", "")]
    extras = paper.get("document_urls", [])
    if isinstance(extras, list):
        candidates.extend(extras)
    candidates = list(dict.fromkeys(value for value in candidates if safe_url(value)))[:3]
    if not candidates:
        result["error"] = "No supported full-text document is available for this reference."
        return result
    owned = client is None
    client = client or httpx.Client(
        timeout=25,
        follow_redirects=False,
        trust_env=False,
        limits=httpx.Limits(max_keepalive_connections=0),
    )
    deadline = time.monotonic() + DOWNLOAD_SECONDS
    try:
        for url in candidates:
            result.update(
                url=url, sha256="", retrieved_at="", pages=[], total_pages=0, truncated=False
            )
            try:
                data, final_url = _download(url, client, deadline)
                result.update(
                    url=final_url,
                    sha256=hashlib.sha256(data).hexdigest(),
                    retrieved_at=datetime.now(UTC).isoformat(),
                )
                extracted = _extract(data)
                result.update(
                    pages=extracted["pages"],
                    total_pages=extracted.get("total_pages", 0),
                    truncated=bool(extracted.get("truncated", False)),
                    isolation=extracted.get("isolation", "unknown"),
                )
                if not any(page.get("text", "").strip() for page in result["pages"]):
                    result.update(
                        status="unavailable",
                        error="No extractable text was found; OCR is not supported.",
                    )
                else:
                    result.update(status="available", error="")
                return result
            except (DocumentError, httpx.HTTPError) as exc:
                result.update(
                    status="failed",
                    error=str(exc)
                    if isinstance(exc, DocumentError)
                    else "The document repository could not be reached within request limits.",
                )
        return result
    finally:
        if owned:
            client.close()
