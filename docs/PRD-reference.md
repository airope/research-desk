# ResearchDesk technical scope

This reference summarizes the product boundary. It is not a delivery schedule or a certification of all acceptance criteria. See [product purpose](../PRODUCT.md) and the [status guide](../PROGRESS.md) for entry points.

## Research dossiers

Turn a scientific question into a reviewable reading dossier: editable search planning, bounded INSPIRE searches, paper selection, supported PDF extraction and passage retrieval, cited draft synthesis and focused follow-up investigation. Preserve the sources supplied to each report and distinguish abstract evidence from PDF-page evidence. A matching quotation supports traceability, not the truth or completeness of a model's conclusion.

Model generation uses an explicitly selected provider. API adapters and the experimental, default-disabled personal Codex adapter share the bounded workflow; neither an API key nor personal CLI authentication is needed for manual INSPIRE search. Optional Elasticsearch retrieval is distinct from model inference. See [providers](llm-providers.md), [investigation](research-investigation.md) and [Elasticsearch](elasticsearch.md).

## Publication catalogues

Import bibliographic CSVs or demonstration records into owner-scoped catalogues, preview bounded INSPIRE acquisition, compare evidence, review possible duplicate records, correct fields and export the catalogue with a change report. Preserve original records and decision history; permit compensating changes without silently erasing provenance. See the [catalogue guide](catalogue-guide.md).

The legacy Crossref/OpenAlex public-metadata demonstration is a separate reconciliation subsystem. Similarity scores are ranking signals, not calibrated probabilities. Automatic association remains disabled while evaluation relies on synthetic and weak DOI-derived labels rather than independent expert annotation.

## Engineering requirements

- Owner-scoped private data and explicit separation from the shared demonstration graph.
- Bounded acquisition, processing and model actions; visible failures, cancellation fencing and recoverable background work.
- Retained source provenance, immutable report evidence and reversible human decisions.
- English, keyboard-accessible interfaces with usable narrow-screen layouts.
- Reproducible tests and clearly qualified evaluation; no invented accuracy, adoption or capacity claims.

See [architecture](architecture.md), [decisions](decisions.md), [validation](validation.md) and [research evaluation](research-evaluation.md) for implementation and assessment details.

## Exclusions and acceptance limits

The supported release boundary is a trusted local workstation, not an Internet-facing or hostile multi-tenant service. Production settings alone do not establish hosting readiness. External exposure requires independently reviewed and tested ingress limits, isolation, authentication, TLS, retention and recovery. See [security](../SECURITY.md) and [deployment](deployment.md).

Arbitrary autonomous browsing, automatic scientific truth assessment, comprehensive OCR/figure interpretation and exhaustive literature coverage are not promised. Source availability does not establish redistribution or third-party processing rights. Review [privacy](privacy-and-network.md) and [third-party notices](third-party-notices.md) before importing or sharing data.
