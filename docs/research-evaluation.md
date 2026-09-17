# Research report evaluation protocol

The software test suite verifies contracts, isolation, citation matching and failure handling. It is not a scientific accuracy score. No independent scientific benchmark has yet been completed.

## Freeze an evaluation set

Select 10 research questions across particle tracking, detector simulation and scientific computing, with 3–10 publicly available papers per question. Save INSPIRE IDs, exact queries, retrieval dates and PDF hashes before comparing retrieval or model variants. Use a separate development set for prompt changes. Record inaccessible documents rather than replacing them silently.

## Independent annotation

A reviewer familiar with each topic records the answerable questions and source passages before seeing the generated answer. A second reviewer checks disputed judgments. Distinguish abstract evidence from physical PDF pages, achieved results from target requirements, and missing evidence from evidence of absence.

For each generated finding, assess:

- Supported: the cited passage supports the complete finding, including quantities and scope.
- Unsupported: evidence contradicts the finding or does not support its material claims.
- Uncertain: available text or domain knowledge is insufficient to judge.

The application's optional assessments save verdict, note, reviewer and time against a report fingerprint; a new generation resets current assessments and retains the old ones in history. Do not call these independent annotations unless the reviewers actually worked independently.

## Report separately

Measure source-ID and page validity, quotation presence, human support rate, unanswered questions and missing relevant evidence. Include the denominator and uncertain count. Record operation times, document failures and passage coverage. Compare abstract-only against PDF passage retrieval on the same frozen selection; do not treat extra citations alone as a quality gain.

Token consumption, subscription quota, cost, retrieval recall and scientific accuracy are currently unmeasured. The UI must not invent values for them. The local demo is a qualitative live check, not this benchmark.
