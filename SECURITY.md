# Security policy

## Supported scope

Research Desk is experimental software for a trusted local workstation. The supplied Compose configuration is a local demonstration, **not a secure Internet deployment recipe**. There is no support SLA or guaranteed security maintenance window; assess the current revision before use.

Do not expose the development server through a public tunnel or bind it to a public interface. Authentication, owner-scoped records, CSRF checks, quotas and parser isolation are defense layers, not certification for hostile multi-tenant hosting. Production settings and [deployment notes](docs/deployment.md) do not replace an independent deployment review.

## Threat model and boundaries

Protect database contents, provider keys, source evidence, session cookies and the workstation itself. Untrusted inputs include CSV records, upstream metadata, PDF bytes, model output and research questions. Threats include cross-user data access, parser exploitation, request forgery, prompt injection, resource exhaustion and unexpected provider spending.

- Keep PostgreSQL and optional Elasticsearch private. Use separate least-privilege credentials, backups and host access controls. Search indexes contain source text, not merely anonymous statistics.
- Replace demonstration secrets before considering any non-local deployment. Use HTTPS and trusted proxy configuration, disable DEBUG, review quotas, isolate workers and validate the actual PDF sandbox on the target operating system.
- Personal Codex is experimental and disabled by default. Keep it restricted to its configured local account and development environment; production refuses activation. Effective CLI tool/configuration isolation is not independently certified. A temporary working directory and read-only flags do not themselves prevent private-file reads. Keep the adapter disabled pending isolated verification with synthetic fixtures and harmless canaries; do not use real user credentials or private files for that verification. Never offer a personal CLI session as a shared service.
- Do not disable PDF confinement to process untrusted documents. Supported download hosts and size/time limits reduce risk but cannot guarantee a PDF is safe.
- Source text can contain prompt injection. Structured outputs and source/quote checks constrain model actions; they do not guarantee truthful, instruction-free or scientifically correct output.
- Job cancellation may leave an in-flight network request running. Quotas are not a financial spending cap.
- The application does not encrypt dossier content at rest or provide a comprehensive retention/compliance system. Operators must protect databases, indexes, logs, exports and backups. See [privacy and network behavior](docs/privacy-and-network.md).

## Ingress and retention requirements

The CSV form's **2 MiB limit is not a transport-body or temporary-disk cap**: multipart parsing can spool files before form rejection. Authentication, CSRF, per-user quotas and `DATA_UPLOAD_MAX_MEMORY_SIZE` are not substitutes for ingress limits. Before any hypothetical external hosting, a controlled front proxy must enforce a bounded total request body (including multipart overhead), request/header/body timeouts and slow-upload protection. Set temporary-disk quotas for proxy buffering and application spooling and prevent direct server access. Test oversized, multiple-file, unauthenticated, missing-CSRF and slow requests, verifying bounded disk writes as well as rejection. External exposure is blocked until these and the wider deployment controls are configured and tested; the source release remains trusted-local-only. See [deployment requirements](docs/deployment.md#mandatory-ingress-limits-before-any-external-hosting).

CSV imports preserve unknown original columns and the uploaded filename. Remove unnecessary columns and identifying filenames before uploading; fields not displayed in the interface can still persist. Operators can access stored data and must define retention and verified cleanup across PostgreSQL, source snapshots/report history, Elasticsearch, logs, exports and backups, as well as any provider-side retention. Use appropriate host/disk and backup encryption. Visible deletion or compaction is not proof of erasure from every copy.

## Export and upstream-content caution

Treat model output, source metadata and downloaded exports as untrusted. Markdown hardening and upstream HTTP content-encoding limits require verification on the exact revision; this policy is not a closure claim for those implementation checks. Use a downstream previewer that disables raw HTML and remote content, and do not assume an attachment is safe merely because it was exported locally. Review source-specific rights before onward processing or sharing.

## Reporting a vulnerability

Use GitHub's **Report a vulnerability** option on the repository's Security tab if it is available. Private reporting must be enabled by the repository maintainer; this document does not imply that it is already enabled.

If no private channel is available, open an issue asking for a private reporting channel **without** including exploit details, credentials, private data or a working attack. Wait for a private channel before sharing sensitive material. Do not test against infrastructure or accounts you do not own or have permission to assess.

A useful private report includes the affected revision, minimal reproduction using synthetic data, expected and actual behavior, impact, environment and any proposed fix. Remove tokens and personal information from logs. Do not send a real database dump or `.env` file.

No response time or bounty is promised. If a secret has been exposed, revoke or rotate it at the provider; removing it from a repository is not sufficient.
