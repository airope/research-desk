import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from catalogues.models import Selection

NOTICE = "All original CSV columns and the uploaded filename are retained"
ADVICE = "Remove private or unneeded columns before uploading"


@pytest.mark.django_db
def test_csv_retention_is_disclosed_before_upload_and_confirmation(client):
    owner = User.objects.create_user("privacy-owner")
    client.force_login(owner)
    url = reverse("catalogues:new")
    page = client.get(url).content.decode()
    assert NOTICE in page
    assert ADVICE in page
    assert page.index(NOTICE) < page.index("Preview catalogue")
    response = client.post(
        url,
        {
            "name": "Privacy example",
            "source": "csv",
            "file": SimpleUploadedFile(
                "fixture.csv", b"title,private_note\nFixture,synthetic note\n"
            ),
        },
    )
    assert response.status_code == 302
    draft = Selection.objects.get()
    preview = reverse("catalogues:preview", args=[draft.pk])
    page = client.get(preview).content.decode()
    assert NOTICE in page
    assert ADVICE in page
    assert page.index(NOTICE) < page.index("Create catalogue from preview")
    assert draft.rows[0]["raw"]["csv_row"]["private_note"] == "synthetic note"
    assert draft.provenance["filename"] == "fixture.csv"
    other = User.objects.create_user("privacy-other")
    client.force_login(other)
    assert client.get(preview).status_code == 404
