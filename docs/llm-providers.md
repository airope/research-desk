# LLM providers

The operator chooses one provider and model for the server. All planning, investigation decisions and report synthesis use that selection. There is no automatic provider/model fallback and no automatic retry of a paid request. API billing is separate from a ChatGPT subscription.

## Configure

Copy `.env.example` to `.env` if it does not exist, then edit it locally. Django loads only this project's `.env`; existing process variables take precedence. Restart both the web process and `research_worker` after changing settings. Never commit the real key.

For OpenAI, these two values are sufficient (the model has a default):

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=replace-with-your-private-key
```

Optional model override:

```dotenv
LLM_MODEL=gpt-4.1
```

Alternatively set `LLM_API_KEY` instead of a provider-specific key. The generic key takes precedence. Keys for other providers are never tried. Adding a key alone does not activate billing: `LLM_PROVIDER` must explicitly select that provider.

## Included providers

These are configurable starting models from the provider documentation, not a claim that they are the newest, cheapest or accessible to every account. Provider availability and model names change; `LLM_MODEL` accepts another supported text-generation model without a code change.

| LLM_PROVIDER | Key variable | Default model | Structured output |
|---|---|---|---|
| `openai` | `OPENAI_API_KEY` | `gpt-4.1` | JSON Schema |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6` | Native forced `research_result` tool response, never executed |
| `gemini` | `GEMINI_API_KEY` | `gemini-3.8-flash` | Google OpenAI-compatible JSON Schema |
| `mistral` | `MISTRAL_API_KEY` | `mistral-small-latest` | JSON object + local schema validation |
| `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-flash` | JSON object + local schema validation |
| `groq` | `GROQ_API_KEY` | `openai/gpt-oss-120b` | JSON Schema |
| `xai` | `XAI_API_KEY` | `grok-4.6` | JSON Schema |
| `openrouter` | `OPENROUTER_API_KEY` | `openai/gpt-4.1` | JSON Schema, required parameter support, upstream fallbacks disabled |
| `openai_compatible` | `LLM_API_KEY` | Required explicitly | Configurable JSON object / JSON Schema |
| `codex` | Official CLI login, no API key | CLI configuration | Existing local structured CLI output |

Models must support Chat Completions and the configured JSON mode, or Anthropic's native tool response. This is not universal compatibility with arbitrary multimodal, embedding, Responses-only or reasoning-only endpoints. Unsupported parameters produce a clear failure, not silent switching. `LLM_OUTPUT_MODE=json_object` can explicitly select a less restrictive wire format for compatible chat models; validation in the application remains mandatory. JSON Schema mode can instead be selected with `LLM_OUTPUT_MODE=json_schema`. Leave this empty for Anthropic.

A local vLLM/LM Studio/Ollama-compatible server can be configured explicitly:

```dotenv
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=http://127.0.0.1:1234/v1
LLM_MODEL=your-installed-model-id
LLM_API_KEY=
LLM_OUTPUT_MODE=json_object
```

The endpoint is server configuration, never an end-user form input. Custom remote endpoints require HTTPS. Unauthenticated HTTP is permitted only on loopback with DEBUG enabled. A production compatible endpoint requires a key and HTTPS. Built-in provider endpoints cannot be overridden accidentally: use `openai_compatible` for a gateway.

## Limits and privacy

- `LLM_MAX_OUTPUT_TOKENS=8192` (allowed 256–32768); `LLM_TIMEOUT_SECONDS=180` (allowed 1–180).
- Input is limited to 500,000 UTF-8 bytes; HTTP responses to 1 MB. Source retrieval has additional, smaller passage budgets.
- Existing user quotas, queue limits, permissions and cancellation fences apply. A cancellation cannot refund an already accepted provider request.
- Questions and selected evidence are transmitted to the configured provider. Only that provider's credential is used; database/search credentials are not part of prompts. Do not supply confidential source material without authorising that destination.
- All API responses undergo local JSON Schema validation, then the existing scientific-source checks (known article, physical PDF page and exact quote). Refusals, truncation and invalid outputs are rejected. Matching a quote does not prove the scientific interpretation is correct.
- Response bodies, API keys and provider error details are not copied into user-facing failures. Redirects are not followed and system proxy variables are ignored.
- Reports record the requested provider/model in their saved provenance, execution panel and Markdown export. Older reports retain their original metadata. Token usage, financial costs and comparative scientific quality are not measured here.
- Paid API providers work in production mode for authenticated active users. Personal Codex remains explicitly development-only and restricted to `RESEARCH_LOCAL_USER`. There is no public signup added by this feature.

## Operations and validation

```sh
uv sync --frozen
uv run python manage.py llm_providers
uv run python manage.py research_worker
```

`llm_providers` lists models and local configuration readiness. It does not contact the paid provider or validate that a key has credits. Compose forwards the documented settings to its services; it does not include `.env` in the image.

The adapter tests use HTTPX MockTransport for every listed provider, with native Anthropic and compatible-chat fixtures. They cover authentication headers, bounded responses, JSON structure, refusals, truncation, unsupported configuration, owner isolation and a full plan → INSPIRE → validated report workflow. No live paid generation was performed during implementation; no provider credentials were supplied for that validation. Real model quality and account-specific access remain to be checked with an authorised key.

## Architecture decision

LiteLLM was evaluated as an existing multi-provider option. This application needs only bounded non-streaming structured text requests, not a proxy, routing service, automatic retries or spend management. Two small wire adapters reuse the existing HTTPX deadline transport; `jsonschema` supplies validation and `python-dotenv` supplies environment loading. This keeps secret routing and retry behaviour inspectable while avoiding a broad provider framework dependency. If routing, many additional native protocols or centralised accounting become requirements, reconsider LiteLLM instead of growing an ad-hoc proxy.

Official references consulted on 2026-09-17:

- [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Anthropic structured outputs and tool schemas](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [Gemini OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai)
- [Mistral chat API](https://docs.mistral.ai/api/endpoint/chat)
- [DeepSeek JSON output](https://api-docs.deepseek.com/guides/json_mode/)
- [Groq structured outputs](https://console.groq.com/docs/structured-outputs)
- [xAI structured outputs](https://docs.x.ai/developers/model-capabilities/text/structured-outputs)
- [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs)
- [LiteLLM](https://docs.litellm.ai/docs/)
