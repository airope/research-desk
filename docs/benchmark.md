# Benchmark: exploratory evidence, no automatic association

The immutable dataset contains 280 records and 200 pairs: 180 synthetic records/150 constructed labels and 100 real records/50 DOI-derived weak labels. No expert or human manual annotations are claimed. SHA256 publication-family assignment gives development/validation/test partitions of 180/66/34 records and 126/51/23 pairs. Labels do not live in the demo database.

Run `python manage.py benchmark` with PostgreSQL available. The command uses the actual application's PostgreSQL candidate query, inserts temporary partition-scoped records, and rolls back those writes. It records the dataset hash, rule configuration, Python and Git revision. The initial repository has no commits; the report says `uncommitted`, not a fabricated revision.

## Final test counts

| Stratum | Pairs | Positive / different / ambiguous | Candidate recall@20 | Identifier suggestion precision | Conservative lexical suggestion precision | End-to-end lexical recall |
|---|---:|---|---|---|---|---|
| synthetic | 15 | 6 / 6 / 3 | 6/6 | 3/3 | 3/3 | 3/6 |
| weak_identifier | 8 | 8 / 0 / 0 | 8/8 | 8/8 | 8/8 | 8/8 |

These are experimental rule suggestions, not automatic associations performed by the application. Actual automatic coverage is zero and automatic precision is undefined. Candidate recall includes an untruncated DOI union, so the DOI-labeled real stratum structurally favors the identifier baseline. Ambiguous cases are counted separately rather than forced into a binary class.

## Errors and limits

The conservative baseline misses same-publication synthetic cases with a removed DOI. On real data, MathML/title formatting differences can depress lexical compatibility even when the DOI matches. The saved report lists each missed match and its actual signal values. Source title markup remains escaped and preserved; a scientifically faithful MathML-to-text normalization remains future work.

The final synthetic positive denominator is only 6, and its pairs share 3 families. A 6/6 candidate result has a Wilson 95% interval about 0.610–1.000; family correlation can make this pair-level interval optimistic. The real stratum has only 8 DOI-weak positives and no independently annotated negative examples. Neither permits a claim of 99% accuracy or worldwide bibliographic coverage.

The split ratio is expected 60/20/20 under a fixed hash, not forcibly balanced after observing labels. The small test set is reported as obtained. No test-set threshold tuning occurred. The separate embedding experiment uses the same partitions and demonstrates why title similarity alone is unsafe; see embedding-experiment.md.

Full machine-readable report: [benchmark-report.json](../data/benchmark-report.json). Data/label generator: [build_benchmark.py](../scripts/build_benchmark.py). The optional larger functional corpus is not added to the frozen evaluation test set.
