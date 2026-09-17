# Third-party notices and data boundaries

## Project license and identity

The project's original code and documentation use the existing [MIT License](../LICENSE). Retain its copyright and permission notice when distributing copies or substantial portions. The historical “Scholarly Record Reconciliation contributors” notice remains in place; the Research Desk product name does not erase earlier attribution.

The project is independent. Names such as INSPIRE, CERN, Crossref, OpenAlex, arXiv and provider/model names identify services or sources; they do not imply affiliation or endorsement. Their trademarks and upstream content are not relicensed by this repository.

## Included data

| Material | Provenance and rights boundary |
|---|---|
| `data/demo.json`, `data/corpus.json` | Crossref and OpenAlex bibliographic metadata; acquisition queries, hashes and source terms are in the matching `.manifest.json` files. Crossref bibliographic metadata is broadly reusable, but copyright-sensitive abstracts are excluded. OpenAlex describes its dataset as CC0. Article full-text licenses are separate. |
| `data/synthetic.json`, `data/examples/catalogue.csv` | Artificial project fixtures, not real publication assertions. See the data READMEs. |
| `data/benchmark.json` | Derived benchmark combining synthetic cases and public metadata; underlying metadata terms still apply. Labels are synthetic or DOI-derived weak supervision, not expert judgments. |
| `data/*-report.json` | Experimental measurements/provenance and, where present, derived metadata examples. They do not grant new rights to upstream material or establish production accuracy. |

Public scholarly metadata can include author names and public scholarly identifiers such as ORCID. It is not anonymous data. Keep source provenance and distinguish metadata permission from article-content permission. See [fixture documentation](../data/README.md).

Primary references:

- [Crossref REST API and reuse notice](https://www.crossref.org/documentation/retrieve-metadata/rest-api/): almost none of the metadata is subject to copyright; some abstracts may be copyrighted by authors or publishers.
- [OpenAlex documentation](https://github.com/ourresearch/openalex-docs): describes the dataset as CC0. Provider access quotas and authentication rules are separate from dataset licensing and can change.

## Live research sources are not bundled fixtures

INSPIRE's [terms of use](https://help.inspirehep.net/knowledge-base/terms-of-use/) permit reuse of HEP metadata under CC0 with caveats: downloading email addresses is prohibited; abstract reuse under those terms is limited to abstracts whose source is arXiv or CERN; keyword fields also have conditions. Downloading content does not transfer intellectual property rights, and reconstructing article full text from snippets is prohibited.

Do not assume every returned abstract is covered by CC0. The research adapter's source-selection policy accepts abstract text only when INSPIRE labels its source exactly `arXiv` or `CERN`, retains the selected source label and marks unsupported-source evidence unavailable. This restriction is present in the adapter; regression verification on the final release revision remains required. It is not a blanket rights clearance and does not retroactively sanitize existing dossiers, snapshots or report history created before the restriction. Review or remove older stored content before onward processing or sharing. Source-specific review remains important for provider prompts, exported reports and public screenshots; absent or unsupported labels must not be treated as permission.

PDFs hosted by arXiv or INSPIRE can have different author/publisher licenses. Availability for download is not a blanket right to redistribute text or send it to an external processor. Operators are responsible for checking applicable terms and permissions. No paper PDFs or live dossier database are part of the committed fixture set described above.

## Dependencies, models and containers

Dependencies retain their own licenses. `pyproject.toml` and `uv.lock` identify Python requirements and resolved packages; the project MIT license does not replace license notices in those distributions. If distributing a built environment, preserve the licenses and notices required by all included direct and transitive dependencies and OS packages, not just the project's license.

The optional `sentence-transformers/all-MiniLM-L6-v2` experiment uses a pinned model documented as Apache-2.0 in its model card. Weights are downloaded to a local cache, not bundled in the repository. Preserve its license and any applicable notices if redistributing the weights; see [the experiment and pinned source](embedding-experiment.md).

PostgreSQL, Python/base images, bubblewrap and the optional Elasticsearch server are separate distributions with their own notices. In particular, do not assume an Elasticsearch server image has the same license as the Python Elasticsearch client, or that a source repository's license covers every binary/image. Review the exact artifact terms before redistributing containers or offering a hosted service. API providers and the optional Codex CLI also have separate service/account terms.

This notice records provenance and operational boundaries, not a complete dependency SBOM or a legal opinion. Adding data, models, assets or dependencies requires another rights review.
