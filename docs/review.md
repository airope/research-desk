# Adversarial review and resolution

Independent team passes inspected modules outside their original implementation ownership, plus root browser/integration checks.

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| R1 | P2 | Actual review states excluded from filter and awaiting count | UI/API support review/insufficient_evidence; regression test; rank latest unresolved evidence first. |
| R2 | P2 | Random UUID tie-break made benchmark retrieval non-reproducible | Stable provider/external-ID ordering, >K equal-title regression, both reports regenerated. |
| R3 | P2 | Withdrawing earlier defer hid still-active acceptance | Derive state from remaining active decision and current evidence; regressions for accepted and stale-source cases. |
| R4 | P1 | Overlong source ID overflowed failure table and poisoned retries | Bounded SHA256 failure key, full offending ID retained in diagnostic payload; PostgreSQL regression. |
| R5 | P1 | OpenAlex null/non-object meta crashed worker outside error handling | Explicit provider schema check and terminal ConnectorError; mocked schema regressions. |
| R6 | P2 | Retry-After >24h incorrectly capped to24h | Preserve full valid deadline; separate inline wait budget; reject absurd/unrepresentable values explicitly. |
| R7 | P2 | Malformed nested bibliographic fields could escape normalization | Explicit typed validation, visible terminal item failures, date/author/type tests. |

Security inspected: ORM/parameterized advisory SQL; Django auth/session/CSRF; curator/operator authorization; escaped untrusted metadata; fixed provider/fixture allowlists; no arbitrary URL/path API; pagination bounds; private application documents excluded. No unresolved high/medium finding from these review passes remains. This is not a formal security audit or a guarantee of no defects.
