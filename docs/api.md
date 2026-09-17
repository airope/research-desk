# API guide

Version prefix `/api/v1`, no trailing slash on resource routes. Read endpoints are public; writes require Django session authentication, CSRF and curator/operator roles. Staff can do both. This application has no API token system. Login is `/accounts/login/`; sessions use native Django protection.

```sh
curl 'http://127.0.0.1:8000/api/v1/candidates?page=1&page_size=20&conflict=false'
curl 'http://127.0.0.1:8000/api/v1/publications?q=Polynomial&page_size=20'
curl 'http://127.0.0.1:8000/health/ready'
```

Replace UUIDs with returned resource IDs. Authenticated session requests must send the CSRF token and session cookie; never put them in committed scripts. Example decision JSON:

```json
{"action":"accept","reason":"Matching edition and identifier reviewed.","expected_revision":1,"idempotency_key":"review-client-unique-request-1"}
```

POST it to `/api/v1/candidates/{id}/decisions`. Replaying the same actor/key/content returns the original decision. Changed content under the same key or a stale revision returns 409. Reload evidence before deciding again. A warning override or rejection of an identical DOI requires a reason.

GET `/api/v1/decisions/{id}/withdraw` returns preview groups, remaining active links and expected_revision. POST the same route with reason, expected_revision and a new idempotency_key to append a compensating event. Another active edge can keep a group connected.

Operators POST `/api/v1/imports` with `provider`, `profile: "demo"` and `idempotency_key`. Only the named offline demo profile is exposed through HTTP; arbitrary paths, URLs and queries are rejected. GET `/api/v1/imports/{id}` includes cursor, counters, lease and failures; POST `/retry` queues eligible failures. External acquisition remains explicit CLI work.

Page size is capped at 100. Invalid filters return a stable error object with code, message, fields and request_id. `/api/v1/schema/` generates OpenAPI from serializers/views; `docs/openapi.yaml` is the validated snapshot. Publication responses retain state, successor IDs, projection provenance and source records. History is paginated.
