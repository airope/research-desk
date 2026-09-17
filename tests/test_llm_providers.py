import json
from unittest.mock import patch

import httpx
import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from research import ai
from research.llm.config import PROVIDERS, ProviderError, configuration
from research.llm.transport import generate

SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


@pytest.fixture(autouse=True)
def provider_config(settings):
    settings.LLM_PROVIDER = "openai"
    settings.LLM_API_KEY = "test-only-private-key"
    settings.LLM_PROVIDER_KEYS = {}
    settings.LLM_MODEL = ""
    settings.LLM_BASE_URL = ""
    settings.LLM_OUTPUT_MODE = ""


def reply(name, data=None):
    data = data if data is not None else {"answer": "supported"}
    if name == "anthropic":
        return {
            "stop_reason": "tool_use",
            "content": [{"type": "tool_use", "name": "research_result", "input": data}],
        }
    return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(data)}}]}


@pytest.mark.parametrize("name", list(PROVIDERS))
def test_every_adapter_authenticates_only_to_its_selected_provider(settings, name):
    settings.LLM_PROVIDER = name
    if name == "openai_compatible":
        settings.LLM_BASE_URL = "https://models.example.org/v1"
        settings.LLM_MODEL = "my-model"
    seen = []

    def handler(request):
        seen.append(request)
        body = json.loads(request.content)
        assert body["model"] == configuration().model
        assert "test-only-private-key" not in request.content.decode()
        assert "test-only-private-key" not in str(request.url)
        if name == "anthropic":
            assert request.headers["x-api-key"] == "test-only-private-key"
            assert request.url.path == "/v1/messages"
            assert body["tool_choice"]["name"] == "research_result"
            assert body["tools"][0]["input_schema"] == SCHEMA
        else:
            assert request.headers["Authorization"] == "Bearer test-only-private-key"
            assert request.url.path.endswith("/chat/completions")
            assert body["response_format"]["type"] in {"json_schema", "json_object"}
        return httpx.Response(200, json=reply(name))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert generate("Research question", SCHEMA, client=client) == {"answer": "supported"}
    assert len(seen) == 1
    assert "test-only-private-key" not in repr(configuration())


@pytest.mark.parametrize("code", [301, 400, 401, 403, 429, 500])
def test_http_errors_do_not_leak_bodies_follow_redirects_or_retry(code):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            code,
            text="private response with test-only-private-key",
            headers={"Location": "https://other.example/"},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError) as failure:
            generate("Question", SCHEMA, client=client)
    assert "test-only-private-key" not in str(failure.value)
    assert len(seen) == 1


@pytest.mark.parametrize("name", ["openai", "anthropic", "deepseek"])
@pytest.mark.parametrize("bad", [{"answer": 12}, {"answer": "ok", "unexpected": True}, {}, []])
def test_invalid_schema_never_publishes(settings, name, bad):
    settings.LLM_PROVIDER = name
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=reply(name, bad)))
    ) as client:
        with pytest.raises(ProviderError, match="invalid structured"):
            generate("Question", SCHEMA, client=client)


@pytest.mark.parametrize("finish", ["length", "content_filter", "tool_calls", None])
def test_incomplete_outputs_rejected(finish):
    data = reply("openai")
    data["choices"][0]["finish_reason"] = finish
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data))
    ) as client:
        with pytest.raises(ProviderError):
            generate("Question", SCHEMA, client=client)


def test_no_provider_inference_or_cross_provider_key_fallback(settings):
    settings.LLM_API_KEY = ""
    settings.LLM_PROVIDER = "anthropic"
    settings.LLM_PROVIDER_KEYS = {"OPENAI_API_KEY": "another-provider-key"}
    with pytest.raises(ProviderError, match="ANTHROPIC_API_KEY"):
        configuration()
    assert not ai.availability()[0]


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.example/v1",
        "https://user:secret@remote.example/v1",
        "https://remote.example/v1?api_key=secret",
        "file:///tmp/api",
    ],
)
def test_custom_base_url_rejects_unsafe_config(settings, url):
    settings.LLM_PROVIDER = "openai_compatible"
    settings.LLM_BASE_URL = url
    settings.LLM_MODEL = "local-model"
    with pytest.raises(ProviderError):
        configuration()


def test_api_is_available_without_debug_or_local_codex(settings):
    settings.DEBUG = False
    settings.RESEARCH_CODEX_ENABLED = False
    with patch("research.ai.subprocess.run") as run:
        assert ai.availability()[0]
        run.assert_not_called()


@pytest.mark.django_db
def test_api_mode_allows_other_authenticated_users_but_preserves_ownership(client, settings):
    user = User.objects.create_user("api-user")
    client.force_login(user)
    assert ai.user_allowed(user)
    response = client.post(
        reverse("research:home"),
        {"question": "Compare particle tracking methods", "year_from": 2020, "limit": 3},
    )
    assert response.status_code == 302
    from research.models import Dossier

    dossier = Dossier.objects.get()
    assert dossier.owner_id == user.pk and dossier.status == "queued"
    client.force_login(User.objects.create_user("outsider"))
    assert client.get(reverse("research:detail", args=[dossier.pk])).status_code == 404
    settings.LLM_PROVIDER = "codex"
    assert not ai.user_allowed(user)


def test_missing_key_or_invalid_json_does_not_launch_codex(settings, monkeypatch):
    from research.llm import transport

    def failure(*a, **kw):
        raise ProviderError("API unavailable")

    monkeypatch.setattr(transport, "generate", failure)
    with patch("research.ai._codex_request") as codex:
        with pytest.raises(ai.AIError, match="API unavailable"):
            ai._request("Question", SCHEMA)
        codex.assert_not_called()


def test_large_response_is_rejected():
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 1_000_001))
    ) as client:
        with pytest.raises(ProviderError, match="size"):
            generate("Question", SCHEMA, client=client)


@pytest.mark.django_db
def test_api_workflow_plans_searches_validates_and_publishes(client, settings, monkeypatch):
    from research import inspire, jobs
    from research.llm import transport
    from research.models import Dossier

    settings.RESEARCH_SEARCH_BACKEND = "local"
    user = User.objects.create_user("api-researcher")
    client.force_login(user)
    quote = "This study compares particle tracking methods using detector data."
    paper = {
        "id": "123",
        "title": "Tracking study",
        "abstract": quote,
        "year": 2024,
        "source_url": "https://inspirehep.net/literature/123",
    }
    evidence = [{"paper_id": "123", "page": 0, "quote": quote}]
    report = {
        "summary": "A tracking comparison.",
        "findings": [{"heading": "Study", "text": "Methods were compared.", "evidence": evidence}],
        "comparison": [
            {
                "paper_id": "123",
                "method": "Comparison",
                "result": "Not reported",
                "limitations": "Not reported",
                "evidence": evidence,
            }
        ],
        "limitations": [],
    }
    calls = []

    def handler(request):
        calls.append(request)
        schema = json.loads(request.content)["response_format"]["json_schema"]["schema"]
        result = (
            {"scope": "Tracking studies", "queries": ["tracking"]}
            if "scope" in schema["properties"]
            else report
        )
        return httpx.Response(200, json=reply("openai", result))

    original_client = httpx.Client
    monkeypatch.setattr(
        transport.httpx,
        "Client",
        lambda **kw: original_client(transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr(inspire, "search", lambda *a, **kw: [paper])
    assert (
        client.post(
            "/", {"question": "Compare particle tracking methods", "year_from": 2020, "limit": 3}
        ).status_code
        == 302
    )
    dossier = Dossier.objects.get()
    jobs.execute(jobs.claim())
    dossier.refresh_from_db()
    assert dossier.status == "draft" and dossier.plan["queries"] == ["tracking"]
    client.post(
        reverse("research:action", args=[dossier.pk]), {"action": "start", "queries": "tracking"}
    )
    jobs.execute(jobs.claim())
    dossier.refresh_from_db()
    assert dossier.status == "ready", dossier.error
    assert dossier.report["llm"] == {"provider": "openai", "model": "gpt-4.1"}
    assert dossier.report["findings"][0]["evidence"][0]["quote"] == quote
    assert len(calls) == 2


def test_settings_load_only_explicit_dotenv_without_overriding_process(tmp_path):
    import os
    import subprocess
    import sys

    environment_file = tmp_path / ".env"
    environment_file.write_text(
        "LLM_PROVIDER=anthropic\nLLM_MODEL=from-file\nANTHROPIC_API_KEY=fixture-only-key\n"
    )
    env = {key: value for key, value in os.environ.items() if key in {"PATH", "HOME"}}
    env["LLM_MODEL"] = "injected-model"
    code = f"""from unittest.mock import patch
from dotenv import load_dotenv as real_load
with patch("dotenv.load_dotenv", side_effect=lambda path, **kwargs: real_load({str(environment_file)!r}, **kwargs)):
    from srr import settings
    assert settings.LLM_PROVIDER == "anthropic"
    assert settings.LLM_MODEL == "injected-model"
    assert settings.LLM_PROVIDER_KEYS["ANTHROPIC_API_KEY"] == "fixture-only-key"
print("dotenv precedence verified")
"""
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, result.stderr
