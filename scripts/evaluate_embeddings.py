"""Frozen, offline-after-download title embedding experiment, never used by the app."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "srr.settings")

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
REVISION = "b8903db39f65d93ae28d49a37c4f3fa90c5f94e0"
MODEL_SHA256 = "6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452"
THRESHOLD = 0.85  # Fixed exploratory probe, not tuned on any split.
FILES = [
    "onnx/model.onnx",
    "tokenizer.json",
    "tokenizer_config.json",
    "config.json",
    "1_Pooling/config.json",
    "README.md",
]


def embedding_candidate_ids(index, members, matrix, k, normalized):
    """Exact DOI union top K cosine, with deterministic ID tie breaking."""
    scores = matrix[index]
    candidates = [
        i for i in range(len(members)) if i != index and normalized[members[i]["id"]]["title"]
    ]
    candidates.sort(key=lambda i: (-float(scores[i]), members[i]["id"]))
    ids = (
        {members[i]["id"] for i in candidates[:k]}
        if normalized[members[index]["id"]]["title"]
        else set()
    )
    doi = normalized[members[index]["id"]]["doi"]
    if doi:
        ids.update(
            r["id"]
            for i, r in enumerate(members)
            if i != index and normalized[r["id"]]["doi"] == doi
        )
    return ids


def encode_titles(titles, cache, offline=False):
    import numpy as np
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer

    paths = {
        name: Path(
            hf_hub_download(
                MODEL, name, revision=REVISION, cache_dir=cache, local_files_only=offline
            )
        )
        for name in FILES
    }
    hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    if hashes["onnx/model.onnx"] != MODEL_SHA256:
        raise ValueError("Frozen ONNX model checksum mismatch")
    pooling = json.loads(paths["1_Pooling/config.json"].read_text())
    if not pooling.get("pooling_mode_mean_tokens") or pooling.get("pooling_mode_cls_token"):
        raise ValueError("Unexpected model pooling configuration")
    tokenizer = Tokenizer.from_file(str(paths["tokenizer.json"]))
    tokenizer.enable_truncation(max_length=256)
    tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 2
    session = ort.InferenceSession(
        str(paths["onnx/model.onnx"]), sess_options=opts, providers=["CPUExecutionProvider"]
    )
    vectors = []
    start = time.perf_counter()
    for offset in range(0, len(titles), 32):
        batch = tokenizer.encode_batch(titles[offset : offset + 32])
        inputs = {
            "input_ids": np.array([x.ids for x in batch], dtype=np.int64),
            "attention_mask": np.array([x.attention_mask for x in batch], dtype=np.int64),
            "token_type_ids": np.array([x.type_ids for x in batch], dtype=np.int64),
        }
        inputs = {node.name: inputs[node.name] for node in session.get_inputs()}
        tokens = session.run(None, inputs)[0]
        mask = inputs["attention_mask"][..., None]
        pooled = (tokens * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1)
        pooled /= np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12)
        vectors.extend(pooled)
    return np.array(vectors), hashes, (time.perf_counter() - start) * 1000


def run(dataset_path, output, cache, offline=False, k=20):
    import django

    django.setup()
    from django.db import transaction
    from rapidfuzz.fuzz import ratio

    from records.evaluation import ratio_result, validate_dataset
    from records.matching import compare_metadata
    from records.models import SourceRecord
    from records.normalization import normalize_record
    from records.services import candidate_ids, ingest_record

    content = Path(dataset_path).read_bytes()
    dataset = json.loads(content)
    by_id = validate_dataset(dataset)
    normalized = {key: normalize_record(r["provider"], r["raw"]) for key, r in by_id.items()}
    all_records = list(by_id.values())
    vectors, hashes, encoding_ms = encode_titles(
        [normalized[r["id"]]["title"] for r in all_records], cache, offline
    )
    vector_by_id = {r["id"]: vectors[i] for i, r in enumerate(all_records)}
    try:
        revision = (
            subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )
    except subprocess.CalledProcessError:
        revision = "uncommitted"
    report = {
        "schema_version": 1,
        "status": "measured",
        "model": MODEL,
        "model_revision": REVISION,
        "model_license": "Apache-2.0",
        "model_file_sha256": hashes,
        "dataset_sha256": hashlib.sha256(content).hexdigest(),
        "git_revision": revision,
        "automatic_integration": False,
        "input_fields": ["title"],
        "k": k,
        "probe_threshold": THRESHOLD,
        "threshold_policy": "Fixed exploratory threshold 0.85 before execution; not selected on test or other splits.",
        "annotation_status": dataset["annotation_status"],
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": {
                name: importlib.metadata.version(name)
                for name in ("onnxruntime", "numpy", "tokenizers", "huggingface-hub")
            },
        },
        "encoding_ms": encoding_ms,
        "splits": {},
        "errors": [],
        "limitations": [
            "Synthetic and DOI weak labels only; no independently verified identity labels.",
            "DOI label circularity and shared upstream providers limit conclusions.",
            "Title-only similarity cannot distinguish identical-title editions, preprints or missing context.",
            "Cosine top K uses a dense matrix only for this small frozen experiment; not a production index.",
            "Title-only probes are uncalibrated suggestions, never probabilities or automatic merges.",
            "Wilson intervals assume independent pairs; family clustering can make them optimistic.",
            "Encoding excludes download/model load; retrieval timings exclude encoding.",
        ],
    }
    for split in ("development", "validation", "test"):
        members = [r for r in all_records if r["split"] == split]
        pairs = [p for p in dataset["pairs"] if by_id[p["left"]]["split"] == split]
        positions = {r["id"]: i for i, r in enumerate(members)}
        import numpy as np

        v = np.array([vector_by_id[r["id"]] for r in members])
        start = time.perf_counter()
        matrix = v @ v.T
        embedding = {
            r["id"]: embedding_candidate_ids(i, members, matrix, k, normalized)
            for i, r in enumerate(members)
        }
        embedding_ms = (time.perf_counter() - start) * 1000
        with transaction.atomic():
            db = {
                r["id"]: ingest_record(
                    r["provider"], "__embedding_experiment__:" + r["id"], r["raw"]
                )[0]
                for r in members
            }
            pool = SourceRecord.objects.filter(pk__in=[r.pk for r in db.values()])
            reverse = {r.pk: key for key, r in db.items()}
            start = time.perf_counter()
            lexical = {
                key: {reverse[pk] for pk in candidate_ids(r, k=k, pool=pool)}
                for key, r in db.items()
            }
            lexical_ms = (time.perf_counter() - start) * 1000
            transaction.set_rollback(True)
        section = {
            "records": len(members),
            "families": len({r["group"] for r in members}),
            "retrieval_ms": {"lexical": lexical_ms, "embedding": embedding_ms},
            "strata": {},
        }
        for origin in ("synthetic", "weak_identifier"):
            subset = [p for p in pairs if p["label_source"] == origin]
            result = {}
            for method, candidates in [("lexical", lexical), ("embedding", embedding)]:

                def found(p):
                    return (
                        p["right"] in candidates[p["left"]] or p["left"] in candidates[p["right"]]
                    )

                positives = [p for p in subset if p["label"] == "same"]
                missing = [
                    p
                    for p in positives
                    if not normalized[p["left"]]["doi"] or not normalized[p["right"]]["doi"]
                ]
                correct = false = ambiguous = guarded_correct = guarded_false = 0
                scores = {"same": [], "different": [], "ambiguous": []}
                for p in subset:
                    left, right = normalized[p["left"]], normalized[p["right"]]
                    score = (
                        float(matrix[positions[p["left"]], positions[p["right"]]])
                        if method == "embedding"
                        else ratio(left["title_key"], right["title_key"]) / 100
                    )
                    scores[p["label"]].append(score)
                    suggested = (
                        found(p) and bool(left["title"] and right["title"]) and score >= THRESHOLD
                    )
                    evidence = compare_metadata(left, right)
                    guarded = (
                        suggested
                        and evidence["signals"]["type"] == "identical"
                        and not evidence["warnings"]
                    )
                    correct += suggested and p["label"] == "same"
                    false += suggested and p["label"] == "different"
                    ambiguous += suggested and p["label"] == "ambiguous"
                    guarded_correct += guarded and p["label"] == "same"
                    guarded_false += guarded and p["label"] == "different"
                    if suggested and p["label"] != "same":
                        report["errors"].append(
                            {
                                "split": split,
                                "method": method,
                                **p,
                                "score": score,
                                "guarded_suggestion": guarded,
                            }
                        )
                result[method] = {
                    "candidate_recall_at_k": ratio_result(
                        sum(found(p) for p in positives), len(positives)
                    ),
                    "without_doi_candidate_recall_at_k": ratio_result(
                        sum(found(p) for p in missing), len(missing)
                    ),
                    "title_probe_precision": ratio_result(correct, correct + false),
                    "title_probe_recall": ratio_result(correct, len(positives)),
                    "false_title_suggestions": false,
                    "ambiguous_title_suggestions": ambiguous,
                    "guarded_probe_precision": ratio_result(
                        guarded_correct, guarded_correct + guarded_false
                    ),
                    "guarded_probe_recall": ratio_result(guarded_correct, len(positives)),
                    "score_summary": {
                        label: {
                            "count": len(values),
                            "mean": sum(values) / len(values) if values else None,
                            "min": min(values) if values else None,
                            "max": max(values) if values else None,
                        }
                        for label, values in scores.items()
                    },
                }
            section["strata"][origin] = result
        report["splits"][split] = section
    Path(output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=str(ROOT / "data/benchmark.json"))
    parser.add_argument("--output", default=str(ROOT / "data/embedding-report.json"))
    parser.add_argument("--cache", default=str(ROOT / ".cache/embeddings"))
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    result = run(args.dataset, args.output, args.cache, args.offline)
    print(
        json.dumps(
            {
                "output": args.output,
                "encoding_ms": result["encoding_ms"],
                "model_revision": REVISION,
            }
        )
    )
