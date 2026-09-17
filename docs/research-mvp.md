> API model providers are now supported: see [configuration](llm-providers.md). The Codex section below describes only the personal local option.

# Research desk MVP

Purpose: turn a scientific question into a bounded INSPIRE reading dossier, a passage-based comparison and a source-linked draft report. This is an independent portfolio project, not an INSPIRE/CERN product or partnership.

## Local launch

Use the existing PostgreSQL setup and Python environment described in README. Run migrations, then start these in separate terminals:

```sh
RESEARCH_CODEX_ENABLED=1 RESEARCH_LOCAL_USER=reviewer .venv/bin/python manage.py runserver 127.0.0.1:8000 --noreload
RESEARCH_CODEX_ENABLED=1 RESEARCH_LOCAL_USER=reviewer .venv/bin/python manage.py research_worker
```

Open http://127.0.0.1:8000/. Existing private catalogues are at `/workspaces/` and remain independent.

The official Codex CLI must be installed and signed in using ChatGPT (`codex login status`). Research desk invokes `codex exec` with structured output, an ephemeral empty working directory, read-only sandbox and disabled shell, browser, plugin and app tools. It does not read auth files, forward API keys or fall back to paid API requests. Subscription-backed mode is disabled by default, requires DEBUG and is restricted to RESEARCH_LOCAL_USER. This is a trusted personal workstation integration, not a publicly hosted model proxy. Actual Codex quota and model availability depend on the signed-in account.

Official references:
- https://learn.chatgpt.com/docs/auth
- https://learn.chatgpt.com/docs/non-interactive-mode
- https://github.com/inspirehep/rest-api-doc

## Demonstration

1. Enter a research question (e.g. compare machine learning approaches for particle tracking), a start year and a limit of 3–20 papers.
2. The selected model proposes up to three INSPIRE queries. Edit and confirm the plan.
3. The worker runs bounded searches, saves papers progressively and synthesizes available abstracts. The activity log records the actual queries and stages.
4. Read an abstract in the source panel. Follow INSPIRE, DOI or arXiv links for the original/full text.
5. Include/exclude papers, then rebuild the report. The previous report is marked stale when the selection changes.
6. Choose **Read available PDFs & update report** to acquire supported arXiv/INSPIRE documents. Follow each citation to the exact physical PDF page and highlighted passage. The source panel shows extraction coverage and the document SHA-256.
7. Open **Ask a follow-up about these papers**, enter a specific question and generate a new focused report. This reuses selected publications; it does not expand the search.
8. Open **Report history** to read earlier reports and their frozen source text. Assess individual findings as supported, unsupported or uncertain, with your own note; these are human assessments, not automated scientific truth scores.
9. Compare methods, inspect quoted passages, export Markdown or BibTeX; the print view can be saved as PDF through the browser print dialog. Execution details show actual operation durations and failures.

## Honest boundaries

- PDF text extraction supports fixed arXiv and INSPIRE file endpoints only. At most six documents per run, 15 MB per download, 40 physical pages and 150,000 extracted characters per document. Page labels printed inside papers may differ from physical PDF positions. No OCR, figure interpretation or faithful table/formula reconstruction.
- Extraction occurs in an OS-confined subprocess with wall/CPU limits and a best-effort memory limit. Redirects are revalidated. PDF binaries are not stored. Workers on the same host share the arXiv request lock; containers must share its file.
- Optional Elasticsearch BM25 ranking and a direct Find passages tab are implemented; see [setup and actual validation status](elasticsearch.md). Without it, deterministic local keyword ranking is used. Both supply at most 4,000 characters per paper and 80,000 in total. It can miss relevant passages. Extracted source text and provenance are frozen with each report; quote validation checks the actual passages supplied to the model.
- Search is bounded, not exhaustive or a systematic literature review. Only first-page results of at most three queries are collected.
- AI summaries can be wrong. Validation checks known source IDs and verbatim quote presence; it does not establish that the quote entails the generated claim or that a scientific result is correct.
- Planning and synthesis are real model calls; there is no synthetic report fallback. With AI unavailable, manual INSPIRE queries and saved papers remain usable.
- Cancellation fences late writes; it does not guarantee immediate termination of an in-flight provider request or reclaim consumed quota.
- A crashed worker is marked failed after ten minutes when a worker next scans the queue. Manual retry retains collected papers and attempts synthesis when papers exist.
- Up to ten previous reports retain their source text and human assessments. History is readable; a side-by-side version diff is not included.
- Focused follow-up questions and a [bounded investigation loop](research-investigation.md) are supported, including reference/citation expansion. No general web agent, MCP server or semantic vector index. No independent scientific-quality benchmark yet; human assessment counts must not be presented as benchmark accuracy.
- No production deployment, paid API calls or subscription sharing were authorized or performed.

## Validation

`pytest tests/test_research*.py` covers owner isolation, local-account restriction, cancellation fencing, duplicate starts, repeated search deduplication, quota failure preservation, manual fallback, source URL construction, HTTP failures, exports, and rejection of fabricated citation IDs/passages. Tests use deterministic model/provider doubles; live checks are recorded separately in PROGRESS.md.
