# ResearchDesk

## Purpose

ResearchDesk helps readers turn scientific questions into source-linked reading dossiers and helps publication curators maintain reviewable bibliographic catalogues. The goal is to make evidence, uncertainty and corrections visible, not to replace scientific judgment or promise automatic verification.

## Research workflow

Start with a question or manual INSPIRE search, review an editable search plan, select publications and compare their evidence. Supported PDF extraction and passage retrieval can supplement abstracts. Generate cited draft reports, ask focused follow-up questions, run bounded investigations and revisit saved report versions with their retained sources.

The operator explicitly selects a model provider: OpenAI, Anthropic, Gemini, Mistral, DeepSeek, Groq, xAI, OpenRouter or a compatible endpoint. Personal Codex is an optional, experimental local adapter, disabled by default; it is not the only generation path or an independently certified isolation boundary. Manual search does not require model generation. See [research workflow](docs/research-mvp.md), [investigation](docs/research-investigation.md) and [provider configuration](docs/llm-providers.md).

## Catalogue workflow

Import a CSV or demonstration catalogue, preview bounded INSPIRE results, compare possible duplicates and conflicting metadata, review additions or corrections, then export an updated catalogue and change report. Owner-scoped records retain original sources, reversible grouping decisions and audit events. The separate shared Crossref/OpenAlex reconciliation demonstration remains available for exploring matching and provenance. See the [catalogue guide](docs/catalogue-guide.md).

These workflows support human review. Similarity scores are not probabilities, and automatic association remains disabled while matching evaluation uses synthetic and weak DOI-derived labels. No institutional integration, affiliation or adoption is claimed.

## Interface and boundaries

Use a compact English workbench: readable publication lists, side-by-side evidence, visible provenance, explicit warnings and recoverable actions. Desktop is primary; narrow screens must remain usable. See [design](DESIGN.md).

The source release supports trusted local use, not public hosting. Dossier content is not encrypted by the application; source text and questions may leave the machine for selected services. Unknown CSV columns and uploaded filenames are retained, so remove unneeded data before import. Neither quoted evidence nor a generated report establishes scientific accuracy or publication rights. Read [security](SECURITY.md), [privacy](docs/privacy-and-network.md) and [third-party notices](docs/third-party-notices.md).

The [status guide](PROGRESS.md) links implementation and verification details. Performance, scientific quality and hosted deployment require their own evidence; the technical scope is not a claim of completed acceptance testing.
