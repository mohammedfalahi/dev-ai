# On-call Voice — Code Standards

> Status: Normative engineering standards  
> Last updated: 2026-09-23

## 1. Engineering principles

- Make unsafe states hard to represent.
- Prefer typed contracts and deterministic state machines to prompt instructions.
- Keep the domain independent of providers and frameworks.
- Fail closed for identity, approval, policy, audit, and kill-switch uncertainty.
- Fail visibly with partial evidence for investigation uncertainty.
- Treat retries, duplicates, cancellation, and timeout as normal behavior.
- Optimize only after measuring; never spend safety margin for aesthetic fluency.
- Tests and evaluation data are part of the product.

## 2. Language and toolchain

### Python

- Python 3.12 or newer within the 3.12 compatibility target until an ADR changes it.
- Use `uv` for workspace/package management and commit the lockfile.
- Use a root `pyproject.toml` with shared configuration.
- Formatting and linting: Ruff.
- Static types: mypy in strict mode. Pyright may be added for editor/SDK coverage, but one tool remains the CI authority.
- Tests: pytest, pytest-asyncio, and Hypothesis where property tests add value.
- Database migrations: Alembic.
- Data contracts: Pydantic v2.

### TypeScript

Use TypeScript only for `apps/console` or a provider SDK that has no acceptable Python path.

- Strict TypeScript configuration.
- No `any` without a documented boundary reason.
- Generated API types come from checked-in JSON/OpenAPI schemas.
- Frontend code cannot reimplement policy decisions.

## 3. Package boundaries

The allowed dependency direction is:

```text
apps → providers/policy/knowledge/observability → domain/contracts
```

Rules:

- `packages/contracts` contains serializable versioned schemas, not business logic.
- `packages/domain` contains pure logic and may depend only on contracts and the standard library.
- `packages/providers` contains ports and adapters. Provider SDK types never leak into domain APIs.
- `packages/policy` owns policy input/output models, bundles, and evaluation wrappers.
- `packages/knowledge` owns ingestion, chunking, retrieval, reranking, and retrieval evaluation.
- Applications compose dependencies; they do not define reusable domain rules.
- Circular imports are forbidden.
- Cross-application imports are forbidden; shared code moves to a package.

## 4. Naming and organization

- Modules, variables, functions: `snake_case`.
- Classes and Pydantic models: `PascalCase`.
- Constants and environment keys: `UPPER_SNAKE_CASE`.
- Event names: past-tense dotted names, such as `incident.created` and `call.connected`.
- Command names: imperative dotted names, such as `incident.suppress`.
- Identifiers use explicit suffixes: `incident_id`, `runbook_chunk_id`, `provider_call_id`.
- Times use `_at`; durations use `_ms` or `_seconds`.
- Boolean names begin with `is_`, `has_`, `can_`, or `should_`.
- Avoid generic modules such as `utils.py`, `helpers.py`, and `common.py`. Name the capability.

Keep files cohesive. Split a module when it mixes domain policy, provider transport, persistence, and orchestration.

## 5. Type and contract rules

- All public functions and methods are fully typed.
- No untyped dictionaries at application boundaries.
- Use Pydantic models for wire, model, tool, and persisted JSON contracts.
- Use dataclasses or immutable value objects for pure internal domain values where serialization is not required.
- Prefer `Enum`/`Literal` for closed states.
- External schemas include `schema_version`.
- Additive compatible changes retain the version; semantic or breaking changes create a new version and migration path.
- Reject unknown fields on safety-critical inputs unless forward compatibility is explicitly designed.
- Use constrained types for confidence, E.164 numbers, digests, timeouts, and bounded text.
- IDs are opaque. Do not encode mutable business meaning in identifiers.

### Time

- Store UTC `timestamptz` values.
- Use timezone-aware `datetime` only.
- Obtain current time through an injectable clock in domain code.
- Use workflow-safe time APIs inside Temporal workflows.
- Render caller-local time only at presentation boundaries.

## 6. Function and class design

- One function should perform one conceptual operation.
- Prefer explicit parameters over hidden globals.
- Use dependency injection at application composition roots.
- Pure functions are preferred for fingerprinting, severity, policy inputs, rank fusion, and state transitions.
- Constructors must not perform network I/O.
- Context managers own resource lifetime.
- Avoid inheritance unless modeling a true substitutable interface; prefer protocols and composition.
- Comments explain why, invariant, or non-obvious risk—not what syntax does.
- Docstrings are required for public interfaces and safety-critical algorithms.

## 7. Async, concurrency, and streaming

- Use `async` only for genuinely asynchronous boundaries.
- Never call blocking SDKs on the event/audio loop; isolate them in a bounded worker thread/process or use an async client.
- Every network operation has an explicit timeout lower than its caller's deadline.
- Use structured concurrency so cancellation propagates.
- Bound fan-out and queue sizes.
- Do not create detached tasks without ownership, cancellation, and error reporting.
- Backpressure is explicit in audio and event streams.
- The voice path streams STT, LLM text, validation units, and TTS; it never waits for a full response when safe sentence-level streaming is possible.
- Investigation concurrency must still honor source rate limits and the global 60-second budget.

## 8. Errors and retries

Define a small typed error taxonomy:

- `ValidationFailure`
- `AuthenticationFailure`
- `PolicyDenied`
- `DeadlineExceeded`
- `TransientProviderFailure`
- `PermanentProviderFailure`
- `DataIntegrityFailure`
- `GroundingFailure`

Rules:

- Do not catch `Exception` without re-raising, translating, or terminating at a process boundary.
- User-safe error messages must not expose secrets or raw provider payloads.
- Retry only failures classified transient.
- Use exponential backoff with jitter and a bounded attempt/time budget.
- A retrying side effect must carry a stable idempotency key.
- Policy denial, validation failure, bad signature, and unsupported operation are not retried.
- Circuit breakers are appropriate for repeated provider failure but cannot bypass required work silently.

## 9. Idempotency

Every externally triggered or side-effecting operation defines:

- Idempotency-key source.
- Uniqueness boundary.
- Storage duration.
- Duplicate response behavior.
- Concurrency behavior.

Examples:

- Alert: `(source, delivery_id)`.
- Temporal workflow: `incident/<incident_id>`.
- Dial attempt: `(incident_id, escalation_step, attempt_number)`.
- Message dispatch: `(approval_id, channel)`.
- Approval: command digest plus transcript state; duplicates return the original record.

Database uniqueness constraints back application-level checks.

## 10. Database standards

- PostgreSQL is the system of record.
- All schema changes use migrations.
- Migrations are forward-safe, observable, and rollback-planned.
- Use expand/migrate/contract for breaking changes.
- Transactions protect multi-row invariants.
- Use database constraints for uniqueness, required provenance, and valid state where practical.
- Never use Redis/NATS as the only copy of durable incident or approval state.
- JSONB is for versioned evidence/brief payloads, not a substitute for core relational columns.
- Queries are bounded and indexed; inspect query plans for hot paths.
- Store embeddings with their model/dimension metadata and content digest.
- Encrypt sensitive fields such as phone numbers and recording references.
- The audit log is append-only and digest chained; application roles cannot update or delete rows.

## 11. Temporal standards

- Workflows are deterministic.
- Network, database, model, filesystem, and random side effects occur only in activities.
- Use Temporal-provided time, random/versioning, and patch APIs.
- Activity inputs/outputs are versioned contracts and remain reasonably small.
- Long-lived incidents use continue-as-new.
- Signals are idempotent and validated.
- Search attributes expose non-sensitive operational status only.
- Retry policies are explicit per activity.
- Workflow histories are replayed in CI before deployment.
- Never place secrets, raw recordings, or oversized log bodies in workflow history.

## 12. LLM and prompt standards

- Prompts are versioned files, reviewed like code, and referenced by digest/version in traces.
- System instructions and untrusted data are separate fields/messages.
- Raw logs, runbooks, alerts, and transcripts are never concatenated as instructions.
- Tool calls use strict input/output schemas.
- Structured model output is validated before use.
- A failed validation does not become best-effort execution.
- Model-generated confidence is calibrated against eval data and never solely controls policy.
- Prompts cannot grant permissions, classify mutation safety, change thresholds, or bypass deterministic checks.
- Keep the voice prompt short. Put investigation results in the ICO, not a growing conversation transcript.
- Summarize or window long conversations while preserving approved state in the deterministic FSM, not only model context.
- Store model/provider/version and token/latency metadata for reproducibility, subject to privacy policy.

## 13. Evidence and grounding standards

Every evidence item includes:

- Stable source ID.
- Source type and system.
- Observation timestamp.
- Collection timestamp.
- Redacted bounded content.
- Content digest.
- Trust/availability metadata.

Every generated claim includes:

- Claim class: observed, retrieved, or inferred.
- Evidence/runbook references.
- Verification result.
- Spoken text.

Rules:

- Observed claims cannot cite inference.
- Retrieved procedural claims cite an eligible runbook chunk.
- Inferred claims are verbally qualified.
- Missing evidence remains an explicit unknown.
- Claim validation runs before TTS and before console publication.
- Validator failure uses a deterministic refusal template.

## 14. Knowledge and retrieval standards

- Preserve source URL, ACL, owner, service, heading path, verification date, and supersession.
- One chunk represents one coherent procedure/decision unit.
- Keep prerequisites, warnings, command, blast radius, and rollback together.
- Never truncate in a way that changes command meaning.
- Lexical and vector search run independently.
- Fuse ranks using RRF; do not average raw BM25 and cosine scores.
- Rerank a bounded fused candidate set.
- Eligibility filtering is deterministic and occurs before procedural use.
- Retrieval thresholds are configuration with eval-backed defaults.
- Reindexing is content-digest based and idempotent.
- No generated postmortem or model summary becomes a verified runbook without owner review.

## 15. Voice standards

- First production path is cascaded STT → text LLM → validator → TTS.
- Use semantic endpointing plus VAD.
- Barge-in cancels queued and active TTS.
- Normal answers are about two spoken sentences; provide more on request.
- Speak times, percentages, identifiers, and commands in a phone-comprehensible form without changing canonical command text during readback.
- Never read Markdown syntax, raw JSON, stack traces, or long IDs aloud.
- Use deterministic wording for consent, refusal, approval, and failure fallbacks.
- A slow lookup gets a brief filler and asynchronous handling; it never blocks audio processing.
- Collect p50/p95 for network, endpointing, STT, LLM TTFT, validation, TTS TTFB, and total turn.
- Recording is off by default. When enabled, announce it before collecting substantive speech.

## 16. Policy and approval standards

- Policy is versioned, testable, and default deny.
- Unknown tools/actions are Tier 2 and denied.
- The model cannot write or select a policy result.
- The canonical command is immutable after proposal; edits create a new proposal and reset approval.
- `GO` counts only in `AWAITING_GO`, as an exact high-confidence utterance according to the configured matcher.
- Destructive/irreversible commands require a second exact confirmation after verbatim readback.
- Caller identity and authorization are explicit policy inputs.
- Audit persistence succeeds before dispatch.
- The same command digest appears in policy input, speech/readback metadata, approval, audit, and dispatch.
- The MVP has no Tier 2 execution adapter. Interfaces that anticipate future execution must default to deny and remain unbound.

## 17. API and webhook standards

- FastAPI endpoints have explicit request/response models.
- Webhooks verify signature before parsing expensive content.
- Enforce content type, byte limit, timestamp tolerance, and rate limit.
- Return stable error codes and correlation IDs.
- Do not expose stack traces.
- OpenAPI changes are reviewed for compatibility and snapshot tested.
- Internal endpoints require service authentication and network policy.
- Provider callbacks are authenticated and idempotent.
- Pagination is required for unbounded collections.

## 18. Logging, metrics, and tracing

### Structured logs

Use JSON logs with event name, severity, correlation IDs, component, and safe fields. Do not interpolate raw payloads into prose logs.

Redact:

- Secrets and authorization headers.
- Full phone numbers.
- Recording URLs.
- Raw transcript/audio unless explicitly routed to protected storage.
- Unbounded logs, traces, and runbook bodies.

### Metrics

Metrics use bounded-cardinality labels. Never use incident IDs, phone numbers, error messages, commands, or user text as metric labels.

### Tracing

Trace external calls and model/tool operations. Store content only when privacy policy permits; otherwise store digest, size, provider, model, token counts, latency, and validation status.

## 19. Security standards

- Secrets come from a secret manager in production; local `.env` is ignored and contains placeholders only.
- Separate read-only and any future mutating credentials.
- Least privilege for database, provider, and cloud roles.
- Verify all inbound signatures and pin expected issuers/audiences.
- Encrypt sensitive fields at rest and use TLS in transit.
- Dependency and container scans run in CI.
- Generate and retain an SBOM for release images.
- Base images are pinned by digest and run as non-root.
- Containers use read-only filesystems where feasible.
- Egress is restricted to required providers.
- Threat-model changes to tools, identity, policy, telephony, recording, and data retention.

## 20. Testing standards

### Test layers

1. **Unit:** pure domain rules, schemas, state transitions, fingerprinting, rank fusion.
2. **Property:** idempotency, fingerprint stability, parser boundaries, approval matching.
3. **Contract:** provider fixtures, OpenAPI, JSON schema, policy I/O.
4. **Integration:** Postgres, Temporal, Redis/NATS, local adapters.
5. **Scenario:** broken-shop fault → incident → ICO → answer/approval outcome.
6. **Evaluation:** analytical accuracy, retrieval, grounding, refusal, voice, latency.
7. **Chaos:** worker kill, provider timeout, database/cache/network failure.
8. **Controlled live:** allowlisted telephony/provider checks outside CI.

### Test rules

- Tests are deterministic by default.
- Time, randomness, model output, and provider callbacks are injectable.
- No test calls a real phone or production service without an explicit live marker and authorization.
- Golden files are reviewed, versioned, and contain no sensitive data.
- Flaky tests are fixed or quarantined with an owner and deadline; they are not blindly retried until green.
- Bugs receive regression tests.
- Safety tests fail the build with no override available to the coding agent.

## 21. CI quality gate

Required jobs:

1. Lockfile and generated-schema consistency.
2. Ruff format check and lint.
3. mypy strict.
4. Unit/property tests with coverage report.
5. Contract and policy tests.
6. Integration tests with containers.
7. Temporal replay tests when histories exist.
8. Retrieval/investigator eval thresholds.
9. Voice/approval eval thresholds when applicable.
10. Secret, dependency, container, and license scans.
11. Migration upgrade/downgrade test.
12. Build reproducible release images and SBOM.

Coverage is a diagnostic, not the only quality measure. New safety-critical branches require explicit tests even if aggregate coverage is high.

## 22. Commits and reviews

- Use Conventional Commits: `feat`, `fix`, `refactor`, `test`, `docs`, `build`, `ci`, `chore`.
- One logical change per commit.
- Commit generated artifacts only when they are source-controlled contracts or required build inputs.
- Pull requests include outcome, risk class, contracts changed, verification evidence, rollout, and rollback.
- R3 changes require security/safety review and two-person approval.
- Architecture changes require an ADR.

## 23. Documentation standard

- Docs describe current behavior, not intent alone.
- Commands are copyable and specify expected output.
- Mark provider/API examples with the verified package/documentation version.
- Avoid undocumented acronyms.
- Update `.context/progress-tracker.md` with each milestone change.
- Never record private chain-of-thought. Record decisions, alternatives, evidence, and rationale.

## 24. Review checklist

- [ ] Correct package boundary and dependency direction.
- [ ] Typed, versioned boundary contracts.
- [ ] Explicit deadline, timeout, retry, idempotency, and cancellation.
- [ ] Safe behavior under partial provider failure.
- [ ] No model-controlled permission or mutation decision.
- [ ] No unsupported procedural output.
- [ ] PII/secrets redacted and retention considered.
- [ ] Unit, integration, scenario, and applicable eval tests.
- [ ] Latency/cost impact measured for hot-path changes.
- [ ] Documentation, ADR, migration, and progress records updated.