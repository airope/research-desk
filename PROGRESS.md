# ResearchDesk status guide

ResearchDesk combines scientific reading dossiers with publication-catalogue review. This page is a stable navigation guide, not a running service log or a claim that every planned feature is complete.

## Implemented scope

- Research questions, editable search plans, bounded INSPIRE acquisition and paper selection.
- Supported PDF extraction, passage retrieval, source-linked synthesis, focused follow-ups and bounded investigation.
- Saved report history with source snapshots, citation checks and exports.
- Explicit operator-selected model providers; optional Elasticsearch retrieval and local keyword fallback.
- Owner-scoped CSV catalogues, source comparison, reversible review decisions, corrections and change reports.
- A separate public-metadata reconciliation demonstration and exploratory evaluation fixtures.

## Documentation and verification

Start with [product scope](PRODUCT.md), [research workflow](docs/research-mvp.md), [bounded investigation](docs/research-investigation.md) and [catalogue guide](docs/catalogue-guide.md). [Technical scope](docs/PRD-reference.md), [architecture](docs/architecture.md) and [design](DESIGN.md) describe the main boundaries.

Use [contributing guidance](CONTRIBUTING.md) for reproducible checks and [deployment notes](docs/deployment.md) for environment-specific acceptance. Historical [validation notes](docs/validation.md) and [subsystem status](docs/status.md) describe their own scope; they are not proof that the current revision passed CI or that a deployment is running.

The source release is for trusted local use. Scientific-quality benchmarking, representative scale testing and independent hosted-deployment security acceptance remain separate work. No autonomous scientific verification, production readiness or universal PDF coverage is claimed. Read [security](SECURITY.md), [privacy](docs/privacy-and-network.md) and [data rights](docs/third-party-notices.md) before processing real material.
