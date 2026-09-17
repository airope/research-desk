import copy

import pytest

from records.evaluation import ratio_result, validate_dataset


def test_small_perfect_sample_has_uncertainty():
    result = ratio_result(5, 5)
    assert result["value"] == 1
    assert result["wilson_95"][0] < 0.6
    assert ratio_result(0, 0)["value"] is None


def test_group_and_identifier_leakage_rejected():
    records = [
        {
            "id": "a",
            "group": "g",
            "split": "test",
            "provider": "crossref",
            "raw": {"DOI": "10.1234/a"},
        },
        {
            "id": "b",
            "group": "g",
            "split": "development",
            "provider": "crossref",
            "raw": {"DOI": "10.1234/a"},
        },
    ]
    with pytest.raises(ValueError, match="group leaks"):
        validate_dataset({"records": records, "pairs": []})
    records = copy.deepcopy(records)
    records[1]["group"] = "other"
    with pytest.raises(ValueError, match="DOI variants"):
        validate_dataset({"records": records, "pairs": []})
