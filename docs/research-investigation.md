# Bounded research investigation

Open a dossier, expand **Investigate an open question**, enter the missing information and start. The existing selected publications form the starting evidence. The local ChatGPT-authenticated Codex model chooses a structured next action; application code validates and executes it. No model-generated code or arbitrary URL is executed.

## Available actions

- `passages`: reformulate a short query for the configured passage backend (Elasticsearch or explicit local fallback).
- `read_page`: inspect up to4,000 characters of an extracted physical PDF page; only known selected paper/page pairs are permitted. This lets the model inspect a table cut by search snippets.
- `read_pdf`: download/extract a selected document through the existing allowlisted, bounded PDF reader. Previously attempted PDFs are skipped; the model can read available pages instead.
- `search`: query INSPIRE for up to two publications, respecting the dossier's starting year.
- `reference`: retrieve one verified outgoing reference from a selected paper (first50 exposed references). This can predate the starting year and is stated in the UI.
- `citations`: search for papers citing a selected record using INSPIRE's `refersto:recid:` operator, with the year filter.
- `finish`: stop acquisition and synthesize the retained evidence.

INSPIRE syntax references: [current search tips](https://help.inspirehep.net/knowledge-base/inspire-paper-search/), [API documentation](https://github.com/inspirehep/rest-api-doc).

## Controls and evidence

A run has at most three decisions/actions, six new papers and twenty total dossier papers. It may finish earlier and stops repeated action signatures. Newly discovered papers are included automatically, while previously excluded records are not re-added. If the dossier already contains twenty papers, external acquisition is skipped. Each model call has the existing180-second timeout; no automatic provider retries or paid API fallback.

The live journal records the action, concise purpose, actual observation, source pages and search backend. Failure observations are retained; an INSPIRE error can be followed by a different decision within the remaining budget. Run durations are measured by the existing telemetry. Cancellation checkpoints prevent subsequent work and final publication after a stop; an in-flight provider request may complete.

Evidence stays bounded to4,000 characters per paper and twenty papers. Newly retrieved passages take priority; older passages survive only within that budget. The final model uses the retained passages directly rather than silently running the original query again. Exact quote/page validation still applies. Reports retain the investigation journal in history and Markdown/print exports.

## Limits

This is a constrained decision loop, not general web browsing, MCP tooling or an exhaustive literature review. It uses a fixed set of application-controlled actions. Three decisions can be insufficient. Chunk truncation, PDF layout and missing references can still cause omissions. A located quotation does not prove a scientific interpretation. External acquisition, citation following and cancellation are covered by deterministic tests; the live demonstration focuses on passage reformulation and direct page reading. No independent scientific quality benchmark has been completed.

## Observed validation (2026-09-17)

206 tests passed in4.05seconds. Live first run reformulated Elasticsearch queries and reached the three-action budget. It exposed missing table rows due to snippet boundaries. After adding direct page reading, a second live run chose page20 of INSPIRE1983941 and then finish; the generated report reproduced all five Table1 rows with exact page citations and identified the results as synthesis estimates. This was a targeted case with the page supplied in the question, not an independent retrieval benchmark. Source highlighting and the action journal were checked in the browser, including390px layout.
