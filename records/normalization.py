"""Conservative, versioned metadata normalization; raw payloads are retained.

DOI syntax follows the common Crossref 10.<4-9 digits>/<non-whitespace>
form. This is syntax validation, never a resolution/existence check. Trailing
punctuation is deliberately retained because it can be part of a DOI suffix.
"""

import re
import unicodedata
from urllib.parse import unquote

NORMALIZATION_VERSION = "1"


def normalize_doi(value):
    if not value:
        return ""
    value = unquote(str(value)).strip()
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)", "", value, flags=re.I)
    value = value.lower()
    return value if re.fullmatch(r"10\.\d{4,9}/\S+", value) else ""


def normalize_title(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def normalize_record(provider, raw):
    if not isinstance(raw, dict):
        raise ValueError("Record payload must be an object.")
    title = raw.get("title") or raw.get("display_name") or ""
    if isinstance(title, list):
        title = title[0] if title else ""
    if not isinstance(title, str):
        raise ValueError("Title must be text.")
    for field in ("DOI", "doi", "type", "abstract"):
        if raw.get(field) is not None and not isinstance(raw[field], str):
            raise ValueError(f"{field} must be text.")
    authors = raw.get("authors") or raw.get("author") or []
    if not isinstance(authors, list):
        raise ValueError("Authors must be a list.")
    if provider == "openalex" and "authorships" in raw:
        if not isinstance(raw["authorships"], list) or any(
            not isinstance(a, dict) or not isinstance(a.get("author"), dict)
            for a in raw["authorships"]
        ):
            raise ValueError("OpenAlex authorships require author objects.")
        authors = [
            {
                "name": a.get("author", {}).get("display_name", ""),
                "orcid": a.get("author", {}).get("orcid"),
            }
            for a in raw["authorships"]
        ]
    for author in authors:
        if not isinstance(author, (str, dict)):
            raise ValueError("Each author must be text or an object.")
        if isinstance(author, dict):
            for field in ("name", "given", "family", "orcid", "ORCID"):
                if author.get(field) is not None and not isinstance(author[field], str):
                    raise ValueError(f"Author {field} must be text.")
    authors = [
        {
            "name": a
            if isinstance(a, str)
            else a.get("name") or " ".join(filter(None, [a.get("given"), a.get("family")])),
            **({"orcid": a.get("ORCID") or a.get("orcid")} if isinstance(a, dict) else {}),
        }
        for a in authors
    ]
    dates = {
        key: raw[key]
        for key in ("published-online", "published-print", "published", "publication_date")
        if raw.get(key)
    }
    for field, value in dates.items():
        if field == "publication_date":
            if not isinstance(value, str) or not re.fullmatch(r"\d{4}(?:-\d{2}){0,2}", value):
                raise ValueError("Publication date must be an ISO date string.")
        else:
            parts = value.get("date-parts") if isinstance(value, dict) else None
            if (
                not isinstance(parts, list)
                or not parts
                or not isinstance(parts[0], list)
                or not 1 <= len(parts[0]) <= 3
                or any(type(part) is not int for part in parts[0])
            ):
                raise ValueError(f"{field} requires numeric date-parts.")
            year_part, *rest = parts[0]
            if (
                not 1 <= year_part <= 9999
                or (rest and not 1 <= rest[0] <= 12)
                or (len(rest) > 1 and not 1 <= rest[1] <= 31)
            ):
                raise ValueError(f"{field} contains invalid date-parts.")
    year = raw.get("year") or raw.get("publication_year")
    if year is not None and (type(year) is not int or not 1 <= year <= 9999):
        raise ValueError("Publication year must be an integer between 1 and 9999.")
    if not year:
        for value in dates.values():
            try:
                year = value["date-parts"][0][0] if isinstance(value, dict) else int(value[:4])
                break
            except (KeyError, IndexError, TypeError, ValueError):
                pass
    source_type = raw.get("type") or ""
    kind = {
        "journal-article": "article",
        "posted-content": "preprint",
        "proceedings-article": "proceedings",
        "book-chapter": "chapter",
    }.get(source_type, source_type)
    return {
        "doi": normalize_doi(raw.get("DOI") or raw.get("doi")),
        "title": title,
        "title_key": normalize_title(title),
        "authors": authors,
        "year": year,
        "dates": dates,
        "type": kind,
        "source_type": source_type,
        "abstract": raw.get("abstract") or "",
    }
