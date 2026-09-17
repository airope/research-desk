#!/usr/bin/env python3
"""Explicit, bounded acquisition. No credentials, purchases, abstracts or PDFs."""

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from records.connectors import MetadataClient, snapshot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--output", default="data/demo.json")
    args = parser.parse_args()
    if not 1 <= args.count <= 500:
        parser.error("count must be 1..500 (up to 1000 provider notices)")
    client = MetadataClient()
    fields = "DOI,title,author,type,published,published-print,published-online,issued,container-title,publisher,URL"
    params = {
        "rows": args.count,
        "filter": "type:journal-article,from-pub-date:2016-01-01,until-pub-date:2016-12-31",
        "select": fields,
        "sort": "published",
        "order": "asc",
    }
    endpoint = "https://api.crossref.org/journals/0031-9007/works"
    crossref = client.get(endpoint, params)["message"]["items"][: args.count]
    records = [
        {"provider": "crossref", "external_id": raw["DOI"], "raw": snapshot("crossref", raw)}
        for raw in crossref
    ]
    requests = [{"url": endpoint, "params": params}]
    for start in range(0, len(crossref), 100):
        dois = [raw["DOI"] for raw in crossref[start : start + 100]]
        oa_params = {
            "filter": "doi:" + "|".join(dois),
            "per_page": 100,
            "select": "id,doi,title,display_name,authorships,type,publication_year,publication_date,language,primary_location",
        }
        result = client.get("https://api.openalex.org/works", oa_params)
        requests.append({"url": "https://api.openalex.org/works", "params": oa_params})
        records.extend(
            {"provider": "openalex", "external_id": raw["id"], "raw": snapshot("openalex", raw)}
            for raw in result["results"]
        )
        time.sleep(0.3)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(records, ensure_ascii=False, indent=2) + "\n").encode()
    path.write_bytes(payload)
    manifest = {
        "acquired_at": datetime.now(timezone.utc).isoformat(),
        "file": path.name,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "count": len(records),
        "counts": {p: sum(r["provider"] == p for r in records) for p in ("crossref", "openalex")},
        "recipe": requests,
        "abstracts_included": False,
        "terms": {
            "crossref": "https://www.crossref.org/documentation/retrieve-metadata/rest-api/",
            "openalex": "https://help.openalex.org/data/how-its-built/",
        },
        "licenses": {
            "crossref": "Bibliographic metadata reuse permitted; copyright-sensitive abstracts excluded.",
            "openalex": "CC0 metadata",
        },
        "limitations": [
            "One journal and year; DOI-linked selection favors exact identifier matches.",
            "OpenAlex includes Crossref upstream; providers are not independent corroboration.",
            "This fixture has no expert-verified labels and is not a representative benchmark.",
        ],
    }
    path.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest["counts"]))


if __name__ == "__main__":
    main()
