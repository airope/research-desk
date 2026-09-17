# Privacy and network behavior

“Local-first” describes where the application and its database can run. It does not mean that every workflow is offline, encrypted, or private from the operator.

## What is stored

PostgreSQL stores accounts and sessions, private catalogue data, source versions and human decisions, research questions and search plans, paper metadata, abstracts and extracted PDF text, report versions, assessments, retrieval provenance and job/activity state. Dossier source snapshots preserve evidence used by saved reports. The application does not add encryption for this content at rest.

CSV intake retains **all original columns**, including unknown or unmapped columns, under the original row data, and records the **uploaded filename**. Unneeded contact details, private notes or identifying filenames can persist even when the interface displays only bibliographic fields. Remove unnecessary columns and rename identifying files **before uploading**; do not rely on field mapping or the preview to discard them.

Database ownership checks restrict application users; they do not hide data from the operator or host administrator. Use appropriate host/disk and backup encryption and access controls.

Downloaded PDF binaries are processed transiently rather than saved as a document library; extracted text and document hashes are persisted. An optional Elasticsearch index stores passage text and identifiers. Exports, browser downloads, printed reports, terminal/server logs and backups can create additional copies outside application access controls.

Historical report limits and source compaction are not a user-data erasure policy. Do not assume deleting or replacing a visible report removes every historical source, index entry, export or backup. Operators must establish retention and verify cleanup across PostgreSQL, source snapshots and report history, Elasticsearch passages, logs, exports, backups and provider-side copies. Search deletion can require `python manage.py reindex_research --purge-orphans` with the write account after an outage or when the web process has only read access; see [deployment maintenance](deployment.md#consumption-limits-and-maintenance). Restoring old backups can reintroduce deleted material. Never publish database dumps or real private dossiers as demonstration fixtures.

## When data leaves the machine

| Action | Destination | Information involved |
|---|---|---|
| Install/build | Python package registries, container registries and OS package mirrors | Package requests and normal connection metadata |
| INSPIRE research or catalogue search | INSPIRE | Search terms/filters, requested record IDs and connection metadata |
| Read supported PDFs | arXiv or INSPIRE | Document identifiers and connection metadata; downloaded text is then processed locally |
| API-based planning, investigation or synthesis | Explicitly configured LLM provider/compatible endpoint | Question, relevant context, selected metadata and source passages needed for that operation |
| Personal Codex generation | Official CLI and its configured service | Prompts and evidence through the operator's existing CLI session; not offline inference |
| Elasticsearch retrieval/indexing | Operator-configured Elasticsearch endpoint | Passage text, scoped identifiers and search queries; remote if the endpoint is remote |
| Explicit external metadata import/acquisition script | Crossref/OpenAlex | Queries, identifiers and any configured request/contact information |
| Optional embedding experiment | Hugging Face on initial download | Model artifact requests; cached inference runs locally |
| Interactive API documentation | External Swagger asset CDN | Browser asset requests; use the committed OpenAPI YAML for offline documentation |
| Follow a publication link | Publisher, DOI resolver, arXiv or another linked site | Normal browser requests governed by that site's policies |

The committed catalogue/reconciliation fixtures need no provider calls after installation. Default external-import disabling applies to the legacy worker, **not** to every network feature: user-triggered INSPIRE searches, PDF acquisition and configured model generation remain separate paths.

## Provider choice and secrets

The operator selects one provider for the server. Questions and selected evidence may be subject to that provider's retention, training, geographic processing, account and billing terms. OpenRouter or another gateway can involve an upstream model vendor as well as the gateway. Review all relevant destinations before submitting confidential material. A local compatible endpoint can keep inference local, but does not make INSPIRE/PDF acquisition offline.

Use environment variables or a private project `.env`; never commit credentials. The application loads only the project `.env`, and process variables take precedence. The generic LLM key takes precedence over the selected provider's named key. There is no automatic selection of another provider or paid-request retry. Restart web and worker processes after changes.

Personal Codex is an experimental, default-disabled local adapter, not offline inference. It depends on the official CLI honoring isolation switches; effective file/tool/configuration isolation is not independently certified. Do not use a personal session on a shared server, or real user credentials/private files in isolation tests. Keep it disabled pending isolated validation. Production settings reject activation.

Provider/model provenance is retained with reports; it is not a bill or complete token-use ledger. Cancelled calls may still consume provider quota. Read [provider configuration](llm-providers.md) and [security guidance](../SECURITY.md).

## Before sharing

Review exports and screenshots for private questions, account names, notes, source passages and credentials. Publicly accessible abstracts and papers are not automatically freely redistributable. Check their specific terms, especially before sending full text to a third-party model or distributing excerpts. See [third-party notices](third-party-notices.md).
