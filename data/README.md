# Metadata fixtures

`demo.json` contains 100 real records: 50 Crossref journal articles from Physical Review Letters (ISSN 0031-9007), 2016, plus 50 corresponding OpenAlex records. `demo.manifest.json` records the exact acquisition queries, timestamp, licenses and file SHA-256. No abstracts or full text are included. Author and bibliographic metadata are retained; unrelated personal/contact fields are excluded by the adapter.

Crossref permits bibliographic metadata reuse, while warning about rights in some abstracts. OpenAlex metadata is CC0. See the source terms in the manifest; article full-text licenses are distinct from metadata terms. The repository's code license does not replace these data terms.

The sample was deliberately selected by DOI to make a small offline demonstration. It is biased towards exact-identifier matches and one journal/year. OpenAlex ingests Crossref data, so the sources are not independent corroboration. These records have no expert-verified labels. DOI-derived labels must remain marked as weak supervision; do not report them as expert-validated accuracy.

`synthetic.json` is a separately named artificial fixture for testing missing identifiers and title negation. It is not real provider metadata or benchmark evidence.

Acquire a fresh 100-record snapshot, explicitly using the public APIs:

```sh
python scripts/acquire_fixtures.py --count 50 --output data/demo.json
```

A bounded larger corpus recipe is `--count 500 --output data/corpus.json` (up to 1,000 provider records, not necessarily 1,000 distinct publications). The OpenAlex batch filter calls fit the documented keyless budget; the command has no payment or credential handling. Actual provider counts can differ, and snapshots change over time. Do not overwrite a benchmark's immutable source snapshot during evaluation. API acquisition is optional; local tests and the demo use committed files.

Official conditions checked 17 September 2026:

- https://www.crossref.org/documentation/retrieve-metadata/rest-api/
- https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/
- https://help.openalex.org/api/authentication/
- https://help.openalex.org/access/example-costs/
- https://help.openalex.org/data/how-its-built/
