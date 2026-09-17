"""Reproducible evaluation. No live demo writes or evaluation labels are mutated."""

import hashlib
import json
import math
import platform
import subprocess
import time
from collections import Counter
from pathlib import Path

from django.db import transaction

from .matching import CONFIG, compare_metadata
from .normalization import normalize_record


def ratio_result(numerator, denominator):
    result = {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
        "wilson_95": None,
    }
    if denominator:
        z, n, p = 1.96, denominator, numerator / denominator
        center = (p + z * z / (2 * n)) / (1 + z * z / n)
        half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
        result["wilson_95"] = [max(0, center - half), min(1, center + half)]
    return result


def validate_dataset(dataset):
    by_id = {r["id"]: r for r in dataset["records"]}
    if len(by_id) != len(dataset["records"]):
        raise ValueError("Duplicate benchmark record ID")
    groups, dois = {}, {}
    for r in dataset["records"]:
        if r["split"] not in {"development", "validation", "test"}:
            raise ValueError("Unknown split")
        if r["group"] in groups and groups[r["group"]] != r["split"]:
            raise ValueError("Publication group leaks between splits")
        groups[r["group"]] = r["split"]
        doi = normalize_record(r["provider"], r["raw"])["doi"]
        if doi and doi in dois and dois[doi] != r["split"]:
            raise ValueError("DOI variants leak between splits")
        if doi:
            dois[doi] = r["split"]
    for p in dataset["pairs"]:
        if p["label"] not in {"same", "different", "ambiguous"}:
            raise ValueError("Unknown label")
        if by_id[p["left"]]["split"] != by_id[p["right"]]["split"]:
            raise ValueError("Cross-split pair")
    return by_id


def baseline_accept(left, right, method):
    signals = compare_metadata(left, right)
    exact = bool(left["doi"] and left["doi"] == right["doi"])
    if method == "identifier":
        return exact
    return (
        exact
        and signals["signals"]["title_similarity"] is not None
        and signals["signals"]["title_similarity"] >= CONFIG["title_compatible"]
        and signals["signals"]["type"] == "identical"
        and not signals["warnings"]
    )


def evaluate(path, k=20):
    from .models import SourceRecord
    from .services import candidate_ids, ingest_record

    raw = Path(path).read_bytes()
    dataset = json.loads(raw)
    by_id = validate_dataset(dataset)
    normalized = {key: normalize_record(r["provider"], r["raw"]) for key, r in by_id.items()}
    try:
        git_revision = (
            subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )
    except subprocess.CalledProcessError:
        git_revision = "uncommitted"
    report = {
        "schema_version": 1,
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "git_revision": git_revision,
        "python": platform.python_version(),
        "config": CONFIG,
        "candidate_k": k,
        "automatic_association_enabled": False,
        "annotation_status": dataset["annotation_status"],
        "limits": [
            "No independent human annotations; no global accuracy claim.",
            "DOI-derived labels favor identifier methods and related providers share upstream data.",
            "Synthetic variants test constructed behavior, not real-world error prevalence.",
            "Wilson intervals treat pairs as independent; family correlation can make these optimistic.",
            "Exact DOI candidates are untruncated in addition to lexical top K.",
            "No thresholds selected on test; initial fixed configuration is exploratory.",
        ],
        "splits": {},
        "errors": [],
    }
    for split in ("development", "validation", "test"):
        members = [r for r in by_id.values() if r["split"] == split]
        pairs = [p for p in dataset["pairs"] if by_id[p["left"]]["split"] == split]
        # Nested transaction is rolled back: neither live catalogue nor human decisions change.
        with transaction.atomic():
            db_records = {}
            for r in members:
                record, _ = ingest_record(r["provider"], "__benchmark__:" + r["id"], r["raw"])
                db_records[r["id"]] = record
            pool = SourceRecord.objects.filter(pk__in=[r.pk for r in db_records.values()])
            start = time.perf_counter()
            candidates = {
                key: set(candidate_ids(record, k=k, pool=pool))
                for key, record in db_records.items()
            }
            candidate_ms = (time.perf_counter() - start) * 1000
            found = {
                key: {other for other, record in db_records.items() if record.pk in ids}
                for key, ids in candidates.items()
            }
            transaction.set_rollback(True)
        section = {
            "records": len(members),
            "families": len({r["group"] for r in members}),
            "pairs": len(pairs),
            "labels": dict(Counter(p["label"] for p in pairs)),
            "candidate_ms": candidate_ms,
            "candidate_count": sum(map(len, found.values())),
            "strata": {},
        }
        for origin in ("synthetic", "weak_identifier"):
            subset = [p for p in pairs if p["label_source"] == origin]
            positives = [p for p in subset if p["label"] == "same"]

            def retrieved(p):
                return p["right"] in found[p["left"]] or p["left"] in found[p["right"]]

            stratum = {
                "pairs": len(subset),
                "ambiguous": sum(p["label"] == "ambiguous" for p in subset),
                "candidate_recall_at_k": ratio_result(
                    sum(retrieved(p) for p in positives), len(positives)
                ),
                "methods": {},
            }
            for method in ("identifier", "lexical"):
                start = time.perf_counter()
                proposed, correct, false, ambiguous = 0, 0, 0, 0
                missing_doi = [
                    p
                    for p in positives
                    if not normalized[p["left"]]["doi"] or not normalized[p["right"]]["doi"]
                ]
                missing_correct = 0
                for p in subset:
                    prediction = retrieved(p) and baseline_accept(
                        normalized[p["left"]], normalized[p["right"]], method
                    )
                    proposed += int(prediction)
                    correct += int(prediction and p["label"] == "same")
                    false += int(prediction and p["label"] == "different")
                    ambiguous += int(prediction and p["label"] == "ambiguous")
                    missing_correct += int(prediction and p in missing_doi)
                    if (prediction and p["label"] != "same") or (
                        not prediction and p["label"] == "same"
                    ):
                        report["errors"].append(
                            {
                                "split": split,
                                "method": method,
                                **p,
                                "retrieved": retrieved(p),
                                "suggested_same": prediction,
                                "evidence": compare_metadata(
                                    normalized[p["left"]], normalized[p["right"]]
                                ),
                            }
                        )
                stratum["methods"][method] = {
                    "experimental_suggestion_precision": ratio_result(correct, correct + false),
                    "end_to_end_recall": ratio_result(correct, len(positives)),
                    "without_doi_recall": ratio_result(missing_correct, len(missing_doi)),
                    "suggestion_coverage": ratio_result(proposed, len(subset)),
                    "ambiguous_suggested": ambiguous,
                    "false_matches": false,
                    "actual_automatic_associations": 0,
                    "actual_automatic_precision": ratio_result(0, 0),
                    "review_cases": len(subset),
                    "latency_ms": (time.perf_counter() - start) * 1000,
                }
            section["strata"][origin] = stratum
        report["splits"][split] = section
    return report
