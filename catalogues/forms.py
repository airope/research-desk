from datetime import date

from django import forms


class CatalogueForm(forms.Form):
    name = forms.CharField(max_length=160, label="Catalogue name")
    source = forms.ChoiceField(
        choices=[("csv", "Upload CSV"), ("demo", "Use demonstration catalogue")],
        widget=forms.RadioSelect,
    )
    file = forms.FileField(
        required=False,
        label="CSV file",
        help_text="UTF-8 CSV, maximum 2 MB and 500 records. Include a title column. Optional: local_id, doi, authors, year, journal.",
    )

    def clean(self):
        data = super().clean()
        if data.get("source") == "csv" and not data.get("file"):
            self.add_error("file", "Choose a CSV file.")
        if data.get("file") and data["file"].size > 2 * 1024 * 1024:
            self.add_error("file", "The maximum file size is 2 MB.")
        return data


class SelectionForm(forms.Form):
    source = forms.ChoiceField(
        choices=[("demo", "Demonstration selection (offline)"), ("inspire", "Search INSPIRE")],
        widget=forms.RadioSelect,
    )
    collaboration = forms.CharField(max_length=120, required=False)
    author = forms.CharField(max_length=120, required=False, label="Author identifier or name")
    institution = forms.CharField(max_length=120, required=False)
    year_from = forms.IntegerField(
        required=False,
        min_value=1000,
        max_value=date.today().year + 1,
        label="Journal publication year from",
    )
    year_to = forms.IntegerField(
        required=False,
        min_value=1000,
        max_value=date.today().year + 1,
        label="Journal publication year to",
    )
    type = forms.ChoiceField(
        choices=[("articles", "Articles"), ("all", "All document types")], label="Document type"
    )
    limit = forms.IntegerField(min_value=1, max_value=100, initial=20, label="Maximum records")

    def __init__(self, data=None, *args, **kwargs):
        if data is not None and data.get("source") == "demo":
            data = data.copy()
            data["type"] = "articles"
            data["limit"] = "20"
            for field in ("collaboration", "author", "institution", "year_from", "year_to"):
                data[field] = ""
        super().__init__(data, *args, **kwargs)

    def clean(self):
        data = super().clean()
        if data.get("year_from") and data.get("year_to") and data["year_from"] > data["year_to"]:
            self.add_error("year_to", "The end year must be on or after the start year.")
        if data.get("source") == "inspire" and not any(
            data.get(key) for key in ("collaboration", "author", "institution")
        ):
            self.add_error(
                None, "Choose a collaboration, author or institution to define the search."
            )
        return data


class EditForm(forms.Form):
    title = forms.CharField(max_length=2000)
    doi = forms.CharField(max_length=300, required=False, label="DOI")
    year = forms.IntegerField(required=False, min_value=1000, max_value=date.today().year + 1)
    journal = forms.CharField(max_length=1000, required=False)
    reason = forms.CharField(
        max_length=2000, widget=forms.Textarea(attrs={"rows": 2}), label="Reason for correction"
    )
    expected_revision = forms.IntegerField(widget=forms.HiddenInput, min_value=1)
    idempotency_key = forms.CharField(widget=forms.HiddenInput, max_length=128)


class ExportForm(forms.Form):
    format = forms.ChoiceField(
        choices=[("catalogue", "Catalogue CSV"), ("changes", "Change report CSV")], label="Export"
    )
    unresolved = forms.ChoiceField(
        choices=[
            ("exclude", "Exclude unresolved entries"),
            ("include", "Include unresolved entries with their status"),
        ],
        widget=forms.RadioSelect,
        initial="exclude",
    )
