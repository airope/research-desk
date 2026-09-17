"""Read-only, bounded INSPIRE search for research dossiers.

Abstracts are provider evidence, not full-text extraction. Source URLs are
constructed from validated identifiers; remote URL fields are never trusted.
"""

import json
import re
from html.parser import HTMLParser

import httpx

from records.normalization import normalize_record
from srr.http_deadline import bounded_stream, raw_chunks

INSPIRE_URL = "https://inspirehep.net/api/literature"
MAX_BYTES = 8 * 1024 * 1024
FIELDS = (
    "control_number,titles,authors.full_name,dois,publication_info,imprints,"
    "preprint_date,abstracts,arxiv_eprints,references.record,documents.url"
)


class SearchError(ValueError):
    """A user-displayable acquisition failure, without remote response bodies."""


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def _text(value):
    if not isinstance(value, str):
        raise SearchError("INSPIRE returned invalid text metadata.")
    parser = _PlainText()
    parser.feed(value)
    return " ".join("".join(parser.parts).split())


def _objects(metadata, key):
    values = metadata.get(key, [])
    if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
        raise SearchError(f"INSPIRE returned invalid {key} metadata.")
    return values


def _paper(hit):
    if not isinstance(hit, dict) or not isinstance(hit.get("metadata"), dict):
        raise SearchError("INSPIRE returned a malformed record.")
    metadata = hit["metadata"]
    identifier = str(hit.get("id") or metadata.get("control_number") or "")
    if not re.fullmatch(r"\d{1,20}", identifier):
        raise SearchError("INSPIRE returned an invalid record identifier.")
    title = next(
        (item.get("title") for item in _objects(metadata, "titles") if item.get("title")), ""
    )
    title = _text(title)
    if not title:
        raise SearchError("INSPIRE returned a record without a title.")
    publications = _objects(metadata, "publication_info")
    publications.sort(key=lambda item: item.get("material", "publication") != "publication")
    year = next((item["year"] for item in publications if item.get("year")), None)
    if year is None:
        dates = [metadata.get("preprint_date", "")]
        dates.extend(item.get("date", "") for item in _objects(metadata, "imprints"))
        year = next(
            (
                int(value[:4])
                for value in dates
                if isinstance(value, str) and re.match(r"^\d{4}(?:-|$)", value)
            ),
            None,
        )
    doi = next(
        (
            item.get("value", "")
            for item in _objects(metadata, "dois")
            if item.get("material", "publication") == "publication"
        ),
        "",
    )
    # INSPIRE terms permit abstract reuse only for these exact source labels:
    # https://help.inspirehep.net/knowledge-base/terms-of-use/
    abstracts = _objects(metadata, "abstracts")
    abstract, abstract_source = "", ""
    for item in abstracts:
        if item.get("source") in ("arXiv", "CERN") and item.get("value"):
            text = _text(item["value"])
            if text:
                abstract, abstract_source = text, item["source"]
                break
    abstract_status = (
        "available"
        if abstract
        else (
            "unavailable_source_not_permitted"
            if any(
                item.get("value") and item.get("source") not in ("arXiv", "CERN")
                for item in abstracts
            )
            else "unavailable"
        )
    )
    raw = {
        "title": title,
        "authors": [_text(item.get("full_name", "")) for item in _objects(metadata, "authors")],
        "year": year,
        "doi": doi,
        "abstract": abstract,
    }
    try:
        normalized = normalize_record("inspire", raw)
    except ValueError as exc:
        raise SearchError("INSPIRE returned invalid bibliographic metadata.") from exc
    fulltext_url = ""
    for item in _objects(metadata, "arxiv_eprints"):
        arxiv_id = item.get("value", "")
        if isinstance(arxiv_id, str) and re.fullmatch(
            r"(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?", arxiv_id
        ):
            fulltext_url = f"https://arxiv.org/pdf/{arxiv_id}"
            break
    references = []
    for item in _objects(metadata, "references"):
        record = item.get("record", {})
        reference = record.get("$ref", "") if isinstance(record, dict) else ""
        match = (
            re.fullmatch(r"https?://inspirehep.net/api/literature/(\d{1,20})", reference)
            if isinstance(reference, str)
            else None
        )
        if match and match[1] not in references:
            references.append(match[1])
    return {
        "id": identifier,
        "title": normalized["title"],
        "authors": [author["name"] for author in normalized["authors"] if author["name"]],
        "year": normalized["year"],
        "doi": normalized["doi"],
        "abstract": normalized["abstract"],
        "abstract_source": abstract_source,
        "abstract_status": abstract_status,
        "source_url": f"https://inspirehep.net/literature/{identifier}",
        "fulltext_url": fulltext_url,
        "references": references,
        "document_urls": [
            item["url"]
            for item in _objects(metadata, "documents")
            if isinstance(item.get("url"), str)
            and re.fullmatch(r"https://inspirehep.net/files/[a-fA-F0-9]{16,128}", item["url"])
        ],
    }


def search(query, limit=8, *, client=None):
    """Return up to 20 papers, preserving full author lists and abstract evidence.

    ``query`` is INSPIRE search syntax, not an arbitrary URL. No full-text PDF
    request is made. An injected httpx client remains owned by its caller.
    """
    if (
        not isinstance(query, str)
        or not query.strip()
        or len(query) > 500
        or any(ord(char) < 32 for char in query)
    ):
        raise SearchError("Enter an INSPIRE query of 1–500 printable characters.")
    if type(limit) is not int or not 1 <= limit <= 20:
        raise SearchError("Request between 1 and 20 papers per search.")
    owned = client is None
    client = client or httpx.Client(
        timeout=20,
        follow_redirects=False,
        trust_env=False,
        limits=httpx.Limits(max_keepalive_connections=0),
    )
    try:
        with bounded_stream(
            client,
            "GET",
            INSPIRE_URL,
            params={"q": query.strip(), "size": limit, "page": 1, "fields": FIELDS},
            timeout=20,
            follow_redirects=False,
        ) as (response, check_deadline):
            if response.status_code == 429:
                raise SearchError("INSPIRE is rate limiting requests. Please retry later.")
            if response.status_code != 200:
                raise SearchError(
                    f"INSPIRE returned HTTP {response.status_code}. Please retry later."
                )
            payload = bytearray()
            for chunk in raw_chunks(response):
                check_deadline()
                if len(payload) + len(chunk) > MAX_BYTES:
                    raise SearchError("INSPIRE response exceeded 8 MB. Request fewer papers.")
                payload.extend(chunk)
        try:
            data = json.loads(payload)
        except (ValueError, UnicodeDecodeError) as exc:
            raise SearchError("INSPIRE returned invalid JSON.") from exc
    except httpx.HTTPError as exc:
        raise SearchError("INSPIRE could not be reached within the request limits.") from exc
    finally:
        if owned:
            client.close()
    hits = data.get("hits") if isinstance(data, dict) else None
    if not isinstance(hits, dict) or not isinstance(hits.get("hits"), list):
        raise SearchError("INSPIRE returned an invalid result list.")
    papers = {}
    for hit in hits["hits"][:limit]:
        paper = _paper(hit)
        papers.setdefault(paper["id"], paper)
    return list(papers.values())
