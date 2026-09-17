"""Human evidence assessments; mechanical quote checks are not scientific review."""

import hashlib
import json


def fingerprint(report):
    content = {k: v for k, v in report.items() if k != "reviews"}
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def counts(report):
    reviews = report.get("reviews", {})
    result = {key: 0 for key in ("supported", "unsupported", "uncertain")}
    for review in reviews.values():
        if review.get("verdict") in result:
            result[review["verdict"]] += 1
    result["reviewed"] = sum(result.values())
    result["total"] = len(report.get("findings", []))
    return result
