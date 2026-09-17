import pytest
from django.http import QueryDict

from catalogues.forms import SelectionForm


@pytest.mark.parametrize(
    "encoded",
    [
        "source=demo",
        "source=demo&limit=&type=&year_from=invalid&year_to=999999",
        "source=demo&limit=999&type=unsupported&collaboration=ignored&author=ignored&institution=ignored",
    ],
)
def test_demo_selection_ignores_missing_or_invalid_live_controls(encoded):
    posted = QueryDict(encoded)
    form = SelectionForm(posted)
    assert form.is_valid(), form.errors
    assert form.cleaned_data["limit"] == 20
    assert form.cleaned_data["type"] == "articles"
    for field in ("collaboration", "author", "institution"):
        assert form.cleaned_data[field] == ""
    assert form.cleaned_data["year_from"] is None
    assert form.cleaned_data["year_to"] is None
    assert posted.urlencode() == QueryDict(encoded).urlencode()


def test_live_selection_keeps_field_validation():
    form = SelectionForm(
        {"source": "inspire", "collaboration": "ATLAS", "limit": "", "type": "articles"}
    )
    assert not form.is_valid()
    assert "limit" in form.errors


def test_demo_defaults_apply_to_keyword_bound_data():
    form = SelectionForm(data={"source": "demo"})
    assert form.is_valid(), form.errors
