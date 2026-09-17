# User catalogue workflow

The homepage is **My catalogues**. Sign in with a local account; catalogues belong to that account, including for staff users. The separate reference review and catalogue remain public demonstration data.

## Start with a file or the offline example

Create catalogue → name → Upload CSV or Use demonstration catalogue → Preview catalogue. CSV is UTF-8 (BOM accepted), comma-separated, title required. Optional local_id, doi, authors, year, journal and type. Author names use semicolons. Original cells, local IDs and source metadata are retained. The downloadable example and incoming demonstration are entirely simulated.

Inspect the preview. Invalid rows have line-numbered errors. Confirmation with errors requires explicitly acknowledging valid-row-only import. Repeated confirmation does not import twice. Caps are 2 MiB and the first 500 baseline rows, with truncation visible; split larger files. A catalogue holds at most 1,000 source entries.

## Find and compare publications

Find publications → offline demonstration or Search INSPIRE. Live searches accept a collaboration, author name/identifier or institution, journal publication years, document type and maximum 1–100 records. Filters combine with AND. Year filters exclude documents without journal publication years, even when all document types are selected. Names may be ambiguous: check authors and affiliations in the provider before relying on a laboratory completeness claim.

INSPIRE results are fetched as one bounded page, with a 20-second request timeout and 8 MiB response limit. Preview the saved selection, upstream total, partial-result warnings and errors, then Analyse this selection. An API error is visible; no fabricated/offline replacement is silently substituted. Confirm imports the exact saved preview, not a fresh search. No worker process is required. Source IDs already present are skipped; a changed previously imported snapshot is reported and retained unchanged. Automatic remote refresh is not implemented.

The result list indicates possible duplicates, conflicting information and new publications to check. These are suggestions from DOI/title evidence, not probabilities or automatic decisions. Included entries are merge targets; pending entries must first be added before other entries can merge into them. Comparisons consider conflicts with all sources already merged into a target. An override reason is required for conflicting merges.

Add to catalogue, merge into an included publication, exclude or mark Needs investigation. Reset decision restores the initial state without erasing history. Reset dependent merged entries before changing their target's membership. Corrections apply only to changed title/DOI/year/journal fields and require a reason. Original snapshots remain immutable.

## Use the output

Export → Catalogue CSV or Change report CSV → choose whether unresolved records are included → Download CSV. Final catalogue rows represent included publications; merged/excluded source entries are omitted, with source IDs and field provenance retained. Included unresolved entries have explicit status and unresolved markers. The change report retains imports, decisions and corrections regardless of that option. UTF-8 CSV formula-like cells are escaped for spreadsheet safety.

No writeback to INSPIRE, CDS or an internal database is performed. The public API still describes the legacy demonstration graph, not private user catalogues. BibTeX/RIS and private JSON APIs are not implemented. CSV exports are not claimed to match an institutional reimport schema.

## Validation and boundaries

A real browser walkthrough created the simulated catalogue, imported its incoming selection, merged one duplicate, deferred a conflicting year, added a new publication and triggered a CSV download. A live UI preview for ATLAS journal year 2024 returned three records with the upstream total 133 and a truncation warning. The numbers are an observed bounded test, not a completeness claim.

Automated tests cover ownership, CSRF, malformed inputs, frozen snapshots, repeated confirmations, stale revisions, group-wide merge conflicts, field corrections, preserved provenance and exported unresolved policy. This is developer validation; independent usability, measured savings and calibrated matching accuracy remain unverified.
