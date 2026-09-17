"""Small bounded metadata clients; response snapshots intentionally omit abstracts."""

import email.utils
import json
import math
import random
import time
from datetime import datetime, timezone

import httpx

from srr.http_deadline import bounded_stream, raw_chunks

MAX_BYTES = 8 * 1024 * 1024
PROVIDERS = {"crossref", "openalex"}
FIELDS = {
    "crossref": (
        "DOI",
        "title",
        "author",
        "type",
        "published",
        "published-print",
        "published-online",
        "issued",
        "container-title",
        "publisher",
        "URL",
        "language",
    ),
    "openalex": (
        "id",
        "doi",
        "title",
        "display_name",
        "authorships",
        "type",
        "publication_year",
        "publication_date",
        "language",
        "primary_location",
    ),
}


class ConnectorError(Exception):
    def __init__(self, code, message, retryable=True, retry_after=None):
        super().__init__(message)
        self.code, self.retryable, self.retry_after = code, retryable, retry_after


def snapshot(provider, raw):
    if provider not in PROVIDERS or not isinstance(raw, dict):
        raise ValueError("Unsupported provider or invalid record.")
    result = {key: raw[key] for key in FIELDS[provider] if key in raw}
    authors_key = "author" if provider == "crossref" else "authorships"
    if authors_key in raw and not isinstance(raw[authors_key], list):
        raise ValueError("Authors must be a list.")
    for author in raw.get(authors_key, []):
        if not isinstance(author, dict):
            raise ValueError("Author entries must be objects.")
        if provider == "openalex" and not isinstance(author.get("author", {}), dict):
            raise ValueError("OpenAlex author must be an object.")
    # Preserve bibliographic author values, without affiliations or personal contact data.
    if provider == "crossref" and isinstance(result.get("author"), list):
        result["author"] = [
            {k: a[k] for k in ("given", "family", "name", "ORCID", "sequence") if k in a}
            for a in result["author"]
            if isinstance(a, dict)
        ]
    if provider == "openalex" and isinstance(result.get("authorships"), list):
        result["authorships"] = [
            {k: a[k] for k in ("author_position", "author", "raw_author_name") if k in a}
            for a in result["authorships"]
            if isinstance(a, dict)
        ]
    return result


def retry_delay(value, attempt, now=None):
    """Parse the full provider deadline; inline waiting is bounded separately."""
    try:
        delay = float(value)
    except (TypeError, ValueError):
        try:
            when = email.utils.parsedate_to_datetime(value)
            delay = (when - (now or datetime.now(timezone.utc))).total_seconds()
        except (TypeError, ValueError, OverflowError):
            delay = 2**attempt + random.uniform(0, 0.5)
    if not math.isfinite(delay) or delay > 100 * 366 * 86400:
        raise ConnectorError(
            "invalid_retry_after",
            "Retry-After is non-finite or exceeds the supported 100-year deadline.",
            False,
        )
    return max(0.0, delay)


class MetadataClient:
    def __init__(
        self, client=None, sleep=time.sleep, heartbeat=None, attempts=3, min_interval=0.25
    ):
        self.client = client or httpx.Client(
            timeout=20,
            follow_redirects=False,
            trust_env=False,
            limits=httpx.Limits(max_keepalive_connections=0),
            headers={"User-Agent": "ScholarlyRecordReconciliation/0.1 (bounded metadata research)"},
        )
        self.sleep, self.heartbeat, self.attempts = sleep, heartbeat, attempts
        self.min_interval, self.last_request = min_interval, None

    def get(self, url, params):
        for attempt in range(self.attempts):
            if self.heartbeat:
                self.heartbeat()
            try:
                if self.last_request is not None:
                    self.sleep(max(0, self.min_interval - (time.monotonic() - self.last_request)))
                self.last_request = time.monotonic()
                with bounded_stream(
                    self.client, "GET", url, params=params, timeout=20, follow_redirects=False
                ) as (response, check_deadline):
                    if response.status_code in (401, 403):
                        raise ConnectorError(
                            "configuration", "Provider denied access; check configuration.", False
                        )
                    if response.status_code == 429 or response.status_code >= 500:
                        raise ConnectorError(
                            "rate_limit" if response.status_code == 429 else "upstream",
                            "Provider temporarily unavailable.",
                        )
                    if response.status_code >= 400:
                        raise ConnectorError(
                            "http_error", f"Provider returned HTTP {response.status_code}.", False
                        )
                    try:
                        data = bytearray()
                        for chunk in raw_chunks(response):
                            check_deadline()
                            if len(data) + len(chunk) > MAX_BYTES:
                                raise ConnectorError(
                                    "response_too_large", "Provider response exceeded 8 MB.", False
                                )
                            data.extend(chunk)
                        payload = json.loads(data)
                        if not isinstance(payload, dict):
                            raise ConnectorError(
                                "invalid_payload", "Provider JSON must be an object.", False
                            )
                        return payload
                    except ValueError as exc:
                        raise ConnectorError(
                            "invalid_json", "Provider returned invalid JSON.", False
                        ) from exc
            except httpx.DecodingError as exc:
                raise ConnectorError(
                    "unsupported_encoding", "Encoded provider responses are not supported.", False
                ) from exc
            except (httpx.TimeoutException, httpx.TransportError):
                error = ConnectorError("transport", "Provider connection failed.")
                response = None
            except ConnectorError as exc:
                if not exc.retryable:
                    raise
                error = exc
                if response is not None and response.headers.get("Retry-After"):
                    error.retry_after = retry_delay(response.headers["Retry-After"], attempt)
            if attempt + 1 == self.attempts:
                raise error
            delay = retry_delay(
                response.headers.get("Retry-After") if response is not None else None,
                attempt,
            )
            if delay > 30:
                raise ConnectorError(
                    "rate_limit",
                    "Provider requested a long Retry-After; retry this import later.",
                    retry_after=delay,
                )
            self.sleep(delay)
        raise ConnectorError("transport", "Provider request failed.")

    def page(self, provider, profile, cursor):
        size = min(profile["page_size"], profile["max_records"] - cursor.get("offset", 0))
        if size <= 0:
            return [], cursor, True
        if provider == "crossref":
            params = {
                "rows": size,
                "cursor": cursor.get("token", "*"),
                "filter": "type:journal-article",
                "select": ",".join(key for key in FIELDS["crossref"] if key != "language"),
            }
            if profile.get("query"):
                params["query.title"] = profile["query"]
            for key, name in [("from_date", "from-pub-date"), ("until_date", "until-pub-date")]:
                if profile.get(key):
                    params["filter"] += f",{name}:{profile[key]}"
            payload = self.get("https://api.crossref.org/works", params).get("message", {})
            if not isinstance(payload, dict):
                raise ConnectorError("invalid_payload", "Invalid Crossref message.", False)
            items, token = payload.get("items", []), payload.get("next-cursor")
        elif provider == "openalex":
            params = {
                "per_page": size,
                "cursor": cursor.get("token", "*"),
                "select": ",".join(FIELDS["openalex"]),
            }
            if profile.get("query"):
                params["search"] = profile["query"]
            filters = ["type:article"]
            for key, name in [
                ("from_date", "from_publication_date"),
                ("until_date", "to_publication_date"),
            ]:
                if profile.get(key):
                    filters.append(f"{name}:{profile[key]}")
            params["filter"] = ",".join(filters)
            payload = self.get("https://api.openalex.org/works", params)
            metadata = payload.get("meta", {})
            if not isinstance(metadata, dict):
                raise ConnectorError("invalid_payload", "OpenAlex meta must be an object.", False)
            items, token = payload.get("results", []), metadata.get("next_cursor")
        else:
            raise ValueError("Unsupported provider.")
        if not isinstance(items, list):
            raise ConnectorError(
                "invalid_payload", "Provider response has no valid result list.", False
            )
        items = items[:size]
        envelopes = [
            {
                "provider": provider,
                "external_id": item.get("DOI" if provider == "crossref" else "id", "")
                if isinstance(item, dict)
                else "",
                "raw": {key: item[key] for key in FIELDS[provider] if key in item}
                if isinstance(item, dict)
                else {},
            }
            for item in items
        ]
        next_cursor = {"offset": cursor.get("offset", 0) + len(items), "token": token}
        return (
            envelopes,
            next_cursor,
            not items or not token or next_cursor["offset"] >= profile["max_records"],
        )
