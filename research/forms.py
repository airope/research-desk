from datetime import date

from django import forms


class QuestionForm(forms.Form):
    question = forms.CharField(
        min_length=12,
        max_length=1500,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Compare machine learning approaches for particle tracking…",
            }
        ),
    )
    year_from = forms.IntegerField(min_value=1900, max_value=date.today().year, initial=2020)
    limit = forms.IntegerField(min_value=3, max_value=20, initial=12)
