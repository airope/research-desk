"""Bounded, database-free catalogue intake. Never downloads abstracts or full text."""

import csv
import hashlib
import io
import json
import re
from datetime import date
from pathlib import Path

import httpx

from records.normalization import normalize_record
from srr.http_deadline import bounded_stream, raw_chunks

CSV_MAX_BYTES = 2 * 1024 * 1024
CSV_MAX_ROWS = 500
INSPIRE_MAX_BYTES = 8 * 1024 * 1024
INSPIRE_URL = "https://inspirehep.net/api/literature"
INSPIRE_FIELDS = "control_number,titles,authors.full_name,dois,document_type,publication_info,imprints,collaborations"
ALIASES = {
    "title": "title",
    "article_title": "title",
    "paper_title": "title",
    "doi": "doi",
    "digital_object_identifier": "doi",
    "authors": "authors",
    "author": "authors",
    "author_names": "authors",
    "year": "year",
    "publication_year": "year",
    "journal_year": "year",
    "journal": "journal",
    "journal_title": "journal",
    "container_title": "journal",
    "local_id": "local_id",
    "id": "local_id",
    "record_id": "local_id",
    "type": "type",
    "document_type": "type",
}


class AcquisitionError(ValueError):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def _preview(rows, errors, total, truncated=False, **extra):
    return {"rows": rows, "errors": errors, "total": total, "truncated": truncated, **extra}


def _normalized(raw):
    normalized = normalize_record("csv", raw)
    normalized["journal"] = raw.get("journal", "")
    return normalized


def parse_csv(content):
    if not isinstance(content, bytes):
        raise AcquisitionError("invalid_file", "Upload CSV file bytes.")
    if len(content) > CSV_MAX_BYTES:
        raise AcquisitionError("file_too_large", "CSV files must be at most 2 MB.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AcquisitionError(
            "invalid_encoding", "Save the CSV as UTF-8 (a BOM is supported)."
        ) from exc
    if "\x00" in text:
        raise AcquisitionError("invalid_file", "CSV files cannot contain NUL bytes.")
    rows, errors, seen_ids, total = [], [], set(), 0
    malformed_tail = False
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = next(reader, None)
        if not header:
            raise AcquisitionError("missing_header", "The CSV needs a header containing title.")
        if len(set(header)) != len(header):
            raise AcquisitionError(
                "duplicate_header", "CSV column headers must be unique, including custom columns."
            )
        fields = [ALIASES.get(re.sub(r"[\s-]+", "_", h.strip().casefold())) for h in header]
        if "title" not in fields:
            raise AcquisitionError("missing_title", "The CSV header must contain title.")
        known = [field for field in fields if field]
        if len(set(known)) != len(known):
            raise AcquisitionError(
                "duplicate_header", "Multiple columns map to the same bibliographic field."
            )
        for values in reader:
            if not values or not any(v.strip() for v in values):
                continue
            total += 1
            line = reader.line_num
            if total > CSV_MAX_ROWS:
                continue
            try:
                if len(values) != len(header):
                    raise ValueError("Column count does not match the header.")
                original_cells = dict(zip(header, values, strict=True))
                values = {
                    key: value.strip() for key, value in zip(fields, values, strict=True) if key
                }
                local_id = values.get("local_id", "")
                if len(local_id) > 512:
                    raise ValueError("Local IDs must be at most 512 characters.")
                if local_id:
                    if local_id in seen_ids:
                        raise ValueError(f"Duplicate local ID: {local_id}.")
                if not values["title"]:
                    raise ValueError("Title is required for each record.")
                if values.get("year") and not re.fullmatch(r"\d{1,4}", values["year"]):
                    raise ValueError("Year must be an integer from 1 to 9999.")
                kind = values.get("type", "article").casefold() or "article"
                kind = {
                    "journal article": "article",
                    "journal-article": "article",
                    "conference paper": "proceedings",
                    "proceedings-article": "proceedings",
                    "book chapter": "chapter",
                }.get(kind, kind)
                if kind not in {
                    "article",
                    "proceedings",
                    "chapter",
                    "book",
                    "preprint",
                    "thesis",
                    "report",
                    "other",
                }:
                    raise ValueError(
                        "Unknown document type; use article, proceedings, chapter, book, preprint, thesis, report or other."
                    )
                raw = {
                    "title": values["title"],
                    "doi": values.get("doi", ""),
                    "authors": [
                        name.strip()
                        for name in values.get("authors", "").split(";")
                        if name.strip()
                    ],
                    "type": kind,
                    "journal": values.get("journal", ""),
                }
                if values.get("year"):
                    raw["year"] = int(values["year"])
                    if raw["year"] == 0:
                        raise ValueError("Year must be an integer from 1 to 9999.")
                raw["csv_row"] = original_cells
                normalized = _normalized(raw)
                if raw["doi"] and not normalized["doi"]:
                    raise ValueError("DOI is malformed; correct it or leave the cell empty.")
                digest = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()[:24]
                if local_id:
                    seen_ids.add(local_id)
                rows.append(
                    {
                        "source": "csv",
                        "external_id": local_id or f"csv:{digest}:{total}",
                        "local_id": local_id,
                        "raw": raw,
                        "normalized": normalized,
                    }
                )
            except ValueError as exc:
                errors.append({"row": line, "message": str(exc)})
    except csv.Error as exc:
        malformed_tail = True
        errors.append(
            {
                "row": reader.line_num,
                "message": f"Malformed CSV: {exc}. Remaining rows were not read.",
            }
        )
    truncated = total > CSV_MAX_ROWS or malformed_tail
    if total > CSV_MAX_ROWS:
        errors.append(
            {
                "row": None,
                "message": f"Only the first {CSV_MAX_ROWS} rows were previewed; reduce or split the file before confirming.",
            }
        )
    return _preview(
        rows,
        errors,
        total,
        truncated,
        total_known=not malformed_tail,
        provenance={
            "source": "csv",
            "sha256": hashlib.sha256(content).hexdigest(),
            "max_rows": CSV_MAX_ROWS,
        },
    )


def _quoted(value):
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 120
        or any(ord(c) < 32 for c in value)
    ):
        raise AcquisitionError(
            "invalid_filter", "Search terms must contain 1–120 printable characters."
        )
    return '"' + value.strip().replace("\\", "\\\\").replace('"', '\\"') + '"'


def _query(filters):
    if not isinstance(filters, dict) or set(filters) - {
        "collaboration",
        "author",
        "institution",
        "year_from",
        "year_to",
        "type",
        "limit",
    }:
        raise AcquisitionError("invalid_filter", "Unknown INSPIRE search filter.")
    clauses = []
    for key, field in [
        ("collaboration", "collaboration"),
        ("author", "author"),
        ("institution", "affiliation"),
    ]:
        if filters.get(key):
            clauses.append(f"{field}:{_quoted(filters[key])}")
    years = {}
    for key in ("year_from", "year_to"):
        value = filters.get(key)
        if value not in (None, ""):
            if (
                isinstance(value, bool)
                or not str(value).isdigit()
                or not 1000 <= int(value) <= date.today().year + 1
            ):
                raise AcquisitionError("invalid_year", "Use a year from 1000 through next year.")
            years[key] = int(value)
    if len(years) == 2 and years["year_from"] > years["year_to"]:
        raise AcquisitionError("invalid_year", "The first year must not exceed the last year.")
    if years:
        clauses.append(
            f"jy {years.get('year_from', 1000)}->{years.get('year_to', date.today().year + 1)}"
        )
    kind = filters.get("type", "articles")
    if kind not in {"articles", "all"}:
        raise AcquisitionError("invalid_type", "Choose articles or all document types.")
    if kind == "articles":
        clauses.append("document_type:article")
    if not any(
        filters.get(key)
        for key in ("collaboration", "author", "institution", "year_from", "year_to")
    ):
        raise AcquisitionError(
            "missing_filter", "Add an author, collaboration, institution or journal year."
        )
    limit = filters.get("limit", 20)
    if isinstance(limit, bool) or not str(limit).isdigit() or not 1 <= int(limit) <= 100:
        raise AcquisitionError("invalid_limit", "Choose between 1 and 100 records.")
    return " and ".join(f"({clause})" for clause in clauses), int(limit)


def _inspire_row(hit):
    if not isinstance(hit, dict) or not isinstance(hit.get("metadata"), dict):
        raise ValueError("INSPIRE record metadata must be an object.")
    metadata = hit["metadata"]
    external_id = str(hit.get("id") or metadata.get("control_number") or "")
    if not re.fullmatch(r"\d{1,20}", external_id):
        raise ValueError("INSPIRE record has no valid source identifier.")
    for key in ("titles", "authors", "dois", "publication_info", "imprints", "collaborations"):
        if key in metadata and (
            not isinstance(metadata[key], list)
            or any(not isinstance(item, dict) for item in metadata[key])
        ):
            raise ValueError(f"INSPIRE {key} must contain objects.")
    titles = metadata.get("titles", [])
    title = next((item.get("title") for item in titles if item.get("title")), "")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("INSPIRE title is missing or invalid.")
    publications = metadata.get("publication_info", [])
    primary = next(
        (
            item
            for item in publications
            if item.get("material", "publication") == "publication" and item.get("year")
        ),
        next((item for item in publications if item.get("year")), {}),
    )
    dois = metadata.get("dois", [])
    doi = next(
        (
            item.get("value")
            for item in dois
            if item.get("material", "publication") == "publication"
        ),
        "",
    )
    doc_types = metadata.get("document_type", [])
    if not isinstance(doc_types, list) or any(not isinstance(t, str) for t in doc_types):
        raise ValueError("INSPIRE document types must be text values.")
    kind = (
        "article"
        if "article" in doc_types
        else {
            "conference paper": "proceedings",
            "thesis": "thesis",
            "book": "book",
            "note": "report",
        }.get(doc_types[0] if doc_types else "", "other")
    )
    raw = {
        "title": title,
        "doi": doi or "",
        "authors": [item.get("full_name", "") for item in metadata.get("authors", [])],
        "type": kind,
        "journal": primary.get("journal_title", ""),
    }
    if primary.get("year") is not None:
        raw["year"] = primary["year"]
    normalized = _normalized(raw)
    if raw["doi"] and not normalized["doi"]:
        raise ValueError(
            "INSPIRE DOI is malformed; the record was not silently imported without it."
        )
    # Keep provider bibliographic evidence; metadata field allowlisting excludes emails/abstracts.
    preserved = {
        "control_number": external_id,
        "titles": [
            {"title": item.get("title", ""), "source": item.get("source", "")} for item in titles
        ],
        "authors": [{"full_name": name} for name in raw["authors"]],
        "dois": [
            {"value": item.get("value", ""), "material": item.get("material", "")} for item in dois
        ],
        "document_type": doc_types,
        "publication_info": [
            {
                key: item[key]
                for key in (
                    "year",
                    "journal_title",
                    "journal_volume",
                    "journal_issue",
                    "page_start",
                    "page_end",
                    "artid",
                    "material",
                )
                if key in item
            }
            for item in publications
        ],
        "collaborations": [
            {"value": item.get("value", "")} for item in metadata.get("collaborations", [])
        ],
    }
    return {
        "source": "inspire",
        "external_id": external_id,
        "local_id": external_id,
        "raw": preserved,
        "normalized": normalized,
    }


def search_inspire(filters, client=None):
    query, limit = _query(filters)
    params = {"q": query, "size": limit, "page": 1, "fields": INSPIRE_FIELDS, "sort": "mostrecent"}
    owned = client is None
    client = client or httpx.Client(
        timeout=20,
        follow_redirects=False,
        trust_env=False,
        limits=httpx.Limits(max_keepalive_connections=0),
    )
    try:
        with bounded_stream(
            client, "GET", INSPIRE_URL, params=params, timeout=20, follow_redirects=False
        ) as (response, check_deadline):
            if response.status_code == 429:
                raise AcquisitionError(
                    "rate_limited",
                    "INSPIRE is rate limiting requests. Wait at least five seconds, or the provider Retry-After period, before trying again.",
                )
            if response.status_code != 200:
                raise AcquisitionError(
                    "provider_error",
                    f"INSPIRE returned HTTP {response.status_code}; no records were imported.",
                )
            payload = bytearray()
            for chunk in raw_chunks(response):
                check_deadline()
                if len(payload) + len(chunk) > INSPIRE_MAX_BYTES:
                    raise AcquisitionError(
                        "response_too_large",
                        "INSPIRE response exceeded 8 MB; reduce the number of requested records.",
                    )
                payload.extend(chunk)
        try:
            data = json.loads(payload)
        except (ValueError, UnicodeDecodeError) as exc:
            raise AcquisitionError("invalid_response", "INSPIRE returned invalid JSON.") from exc
    except httpx.HTTPError as exc:
        raise AcquisitionError(
            "provider_unavailable",
            "INSPIRE could not be reached within the request limits. Retry later.",
        ) from exc
    finally:
        if owned:
            client.close()
    hits = data.get("hits") if isinstance(data, dict) else None
    if not isinstance(hits, dict) or not isinstance(hits.get("hits"), list):
        raise AcquisitionError("invalid_response", "INSPIRE returned an invalid result list.")
    total = hits.get("total", len(hits["hits"]))
    if isinstance(total, dict):
        total = total.get("value")
    if type(total) is not int or total < 0:
        raise AcquisitionError("invalid_response", "INSPIRE returned an invalid result count.")
    rows, errors, seen = [], [], set()
    for index, hit in enumerate(hits["hits"][:limit], 1):
        try:
            row = _inspire_row(hit)
            if row["external_id"] in seen:
                raise ValueError("Duplicate INSPIRE record ID in the response.")
            seen.add(row["external_id"])
            rows.append(row)
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            errors.append({"row": index, "message": str(exc)})
    return _preview(
        rows,
        errors,
        total,
        total > len(hits["hits"][:limit]),
        query=query,
        provenance={
            "source": "inspire",
            "endpoint": INSPIRE_URL,
            "params": params,
            "retrieved": len(hits["hits"][:limit]),
            "terms": "https://inspirehep.net/terms-of-use",
            "date_semantics": "Journal publication year; preprint dates can differ.",
        },
    )


def demo_incoming():
    """Invented incoming records aligned with the bundled sample catalogue."""
    sample = Path(__file__).resolve().parents[1] / "data" / "examples" / "catalogue.csv"
    baseline = parse_csv(sample.read_bytes())["rows"]
    rows = []
    for index, item in enumerate(baseline[:2], 1):
        raw = dict(item["raw"])
        if index == 2:
            raw["year"] += 1
        rows.append(
            {
                "source": "simulated",
                "external_id": f"incoming-{index}",
                "local_id": f"INCOMING-{index}",
                "raw": raw,
                "normalized": _normalized(raw),
            }
        )
    raw = {
        "title": "Simulated calorimeter stability experiment",
        "authors": ["F. Example"],
        "year": 2025,
        "type": "article",
        "journal": "Example Physics Journal",
        "doi": "",
    }
    rows.append(
        {
            "source": "simulated",
            "external_id": "incoming-3",
            "local_id": "INCOMING-3",
            "raw": raw,
            "normalized": _normalized(raw),
        }
    )
    return _preview(
        rows,
        [],
        len(rows),
        provenance={
            "source": "simulated",
            "note": "Invented demonstration records, not real publications: one matching title, one date change, and one new title.",
        },
    )
