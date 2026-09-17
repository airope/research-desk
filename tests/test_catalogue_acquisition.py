import httpx
import pytest

from catalogues.acquisition import AcquisitionError, demo_incoming, parse_csv, search_inspire


def mock_client(payload=None, status=200, handler=None):
    return httpx.Client(
        transport=httpx.MockTransport(
            handler or (lambda request: httpx.Response(status, json=payload))
        )
    )


def hit(recid="123", **metadata):
    return {
        "id": recid,
        "metadata": {
            "titles": [{"title": "Detector study"}],
            "authors": [{"full_name": "Example, A."}],
            "document_type": ["article"],
            "publication_info": [{"year": 2024, "journal_title": "JHEP"}],
            **metadata,
        },
    }


def test_csv_bom_aliases_and_semicolon_authors():
    result = parse_csv(
        "\ufeffid,Paper Title,DOI,Author Names,Publication Year,journal,type\nLOCAL-7,Detector study,https://doi.org/10.1234/TEST,A. Example; B. Example,2024,JHEP,journal article\n".encode()
    )
    row = result["rows"][0]
    assert row["local_id"] == row["external_id"] == "LOCAL-7"
    assert row["normalized"]["doi"] == "10.1234/test"
    assert row["normalized"]["authors"] == [{"name": "A. Example"}, {"name": "B. Example"}]
    assert row["normalized"]["type"] == "article" and row["normalized"]["year"] == 2024
    assert result["errors"] == []


def test_csv_partial_errors_and_duplicate_ids():
    result = parse_csv(
        b"local_id,title,year\na,Valid,2024\na,Duplicate,2024\nb,,2024\nc,Bad year,today\n"
    )
    assert len(result["rows"]) == 1 and result["total"] == 4
    assert [e["row"] for e in result["errors"]] == [3, 4, 5]


@pytest.mark.parametrize(
    "content,code",
    [
        (b"author\nExample\n", "missing_title"),
        (b"title\n\xff", "invalid_encoding"),
        (b"title,article_title\nA,B", "duplicate_header"),
        (b"x" * (2 * 1024 * 1024 + 1), "file_too_large"),
    ],
)
def test_csv_file_errors(content, code):
    with pytest.raises(AcquisitionError) as caught:
        parse_csv(content)
    assert caught.value.code == code


def test_csv_row_cap_and_malformed_tail():
    result = parse_csv(("title\n" + "Study\n" * 501).encode())
    assert len(result["rows"]) == 500 and result["total"] == 501 and result["truncated"]
    result = parse_csv(b'title\nValid\n"unterminated')
    assert len(result["rows"]) == 1 and result["errors"]


def test_inspire_request_bounded_and_quoted_no_doi_id_preserved():
    def handler(request):
        assert request.url.host == "inspirehep.net"
        assert request.url.params["size"] == "2" and request.url.params["page"] == "1"
        assert "abstract" not in request.url.params["fields"]
        assert '\\"' in request.url.params["q"]
        return httpx.Response(200, json={"hits": {"total": 20, "hits": [hit()]}})

    result = search_inspire(
        {
            "collaboration": 'ATLAS" or title:*',
            "year_from": 2024,
            "year_to": 2024,
            "type": "articles",
            "limit": 2,
        },
        client=mock_client(handler=handler),
    )
    row = result["rows"][0]
    assert row["external_id"] == "123" and row["normalized"]["doi"] == ""
    assert row["normalized"]["year"] == 2024 and row["normalized"]["journal"] == "JHEP"
    assert result["total"] == 20 and result["truncated"]


def test_inspire_partial_invalid_and_multiple_dois_raw_preserved():
    good = hit(
        dois=[{"value": "10.1234/good"}, {"value": "10.1234/erratum", "material": "erratum"}]
    )
    result = search_inspire(
        {"author": "Example"},
        client=mock_client({"hits": {"total": 2, "hits": [good, {"id": "bad", "metadata": {}}]}}),
    )
    assert result["rows"][0]["normalized"]["doi"] == "10.1234/good"
    assert len(result["rows"][0]["raw"]["dois"]) == 2
    assert len(result["errors"]) == 1


@pytest.mark.parametrize(
    "filters",
    [
        {"limit": 0},
        {"author": "A", "limit": 101},
        {"author": "A", "year_from": 2025, "year_to": 2024},
        {"author": "A", "query": "*"},
        {"author": "A\nB"},
    ],
)
def test_invalid_filters_never_request(filters):
    def handler(request):
        pytest.fail("No request expected")

    with pytest.raises(AcquisitionError):
        search_inspire(filters, client=mock_client(handler=handler))


@pytest.mark.parametrize("status,code", [(429, "rate_limited"), (503, "provider_error")])
def test_inspire_failures_surface_without_retries(status, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status)

    with pytest.raises(AcquisitionError) as caught:
        search_inspire({"author": "Example"}, client=mock_client(handler=handler))
    assert caught.value.code == code and len(calls) == 1


def test_inspire_invalid_shape_timeout_and_response_cap(monkeypatch):
    with pytest.raises(AcquisitionError, match="invalid result list"):
        search_inspire({"author": "Example"}, client=mock_client({"hits": None}))

    def timeout(request):
        raise httpx.ReadTimeout("test", request=request)

    with pytest.raises(AcquisitionError) as caught:
        search_inspire({"author": "Example"}, client=mock_client(handler=timeout))
    assert caught.value.code == "provider_unavailable"
    monkeypatch.setattr("catalogues.acquisition.INSPIRE_MAX_BYTES", 10)
    with pytest.raises(AcquisitionError) as caught:
        search_inspire({"author": "Example"}, client=mock_client({"hits": {"hits": []}}))
    assert caught.value.code == "response_too_large"


def test_offline_demo_is_explicitly_simulated():
    result = demo_incoming()
    assert len(result["rows"]) == 3
    assert all(row["source"] == "simulated" for row in result["rows"])
    assert result["rows"][0]["normalized"]["title"] == "Simulated detector calibration study"
    assert result["rows"][1]["normalized"]["year"] == 2025


def test_csv_retains_original_unknown_columns_and_cell_spacing():
    result = parse_csv(b"local_id,title,custom lab note\n A , Study , private note \n")
    row = result["rows"][0]
    assert row["local_id"] == "A"
    assert row["raw"]["csv_row"] == {
        "local_id": " A ",
        "title": " Study ",
        "custom lab note": " private note ",
    }


def test_csv_invalid_first_row_does_not_reserve_local_identifier():
    result = parse_csv(b"local_id,title\nA,\nA,Corrected\n")
    assert len(result["errors"]) == 1 and len(result["rows"]) == 1
    assert result["rows"][0]["local_id"] == "A"


def test_malformed_tail_reports_unknown_coverage():
    result = parse_csv(b'title\nValid\n"unterminated')
    assert result["truncated"] and not result["total_known"]


def test_inspire_invalid_doi_cannot_silently_become_missing():
    result = search_inspire(
        {"author": "Example"},
        client=mock_client({"hits": {"total": 1, "hits": [hit(dois=[{"value": "not-a-doi"}])]}}),
    )
    assert result["rows"] == [] and "DOI is malformed" in result["errors"][0]["message"]


def test_duplicate_custom_headers_do_not_silently_lose_original_cells():
    with pytest.raises(AcquisitionError) as caught:
        parse_csv(b"title,note,note\nStudy,A,B\n")
    assert caught.value.code == "duplicate_header"


def test_inspire_full_name_author_projection_is_preserved():
    names = ["Aad, Georges", "Aakvaag, Erlend"]
    result = search_inspire(
        {"collaboration": "ATLAS", "year_from": 2024, "year_to": 2024, "limit": 1},
        client=mock_client(
            {
                "hits": {
                    "total": 1,
                    "hits": [hit("2836178", authors=[{"full_name": name} for name in names])],
                }
            }
        ),
    )
    row = result["rows"][0]
    assert row["raw"]["authors"] == [{"full_name": name} for name in names]
    assert row["normalized"]["authors"] == [{"name": name} for name in names]
