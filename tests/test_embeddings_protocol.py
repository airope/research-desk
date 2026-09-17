"""Protocol checks run without downloading a model or installing optional extras."""

import json
from pathlib import Path

import pytest

from records.evaluation import validate_dataset
from scripts.evaluate_embeddings import REVISION, THRESHOLD, embedding_candidate_ids


def test_embedding_candidates_keep_exact_identifiers_beyond_k():
    members = [{"id": key} for key in ["a", "b", "c", "d"]]
    normalized = {r["id"]: {"doi": "10.1234/shared", "title": "Title"} for r in members}
    assert embedding_candidate_ids(0, members, [[1, 0.9, 0.8, 0.7]], 1, normalized) == {
        "b",
        "c",
        "d",
    }


def test_embedding_candidates_have_stable_ties_and_exclude_self():
    members = [{"id": key} for key in ["a", "b", "c"]]
    normalized = {r["id"]: {"doi": "", "title": "Title"} for r in members}
    assert embedding_candidate_ids(0, members, [[1, 1, 1]], 1, normalized) == {"b"}


def test_missing_title_does_not_create_arbitrary_cosine_candidates():
    members = [{"id": key} for key in ["a", "b"]]
    normalized = {"a": {"doi": "", "title": ""}, "b": {"doi": "", "title": "Present"}}
    assert embedding_candidate_ids(0, members, [[1, 0.5]], 20, normalized) == set()


def test_model_and_probe_are_frozen():
    assert len(REVISION) == 40
    int(REVISION, 16)
    assert THRESHOLD == 0.85


def test_benchmark_families_cannot_leak_between_splits():
    dataset = {
        "records": [
            {"id": "a", "group": "one", "split": "development", "provider": "crossref", "raw": {}},
            {"id": "b", "group": "one", "split": "test", "provider": "crossref", "raw": {}},
        ],
        "pairs": [],
    }
    with pytest.raises(ValueError, match="leaks"):
        validate_dataset(dataset)


def test_committed_report_declares_scope_and_measured_model():
    report_path = Path(__file__).resolve().parents[1] / "data/embedding-report.json"
    if not report_path.exists():
        pytest.skip("Report has not been generated in this checkout.")
    report = json.loads(report_path.read_text())
    assert report["automatic_integration"] is False
    assert report["input_fields"] == ["title"]
    assert report["model_revision"] == REVISION
    assert "No human" in report["annotation_status"]
    assert len(report["model_file_sha256"]["onnx/model.onnx"]) == 64
