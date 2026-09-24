# On-call Voice — Build Plan

> Status: Execution roadmap  
> Planning unit: One-week milestones  
> Last updated: 2026-09-23

## 1. Planning policy

This plan deliberately validates **incident analysis, retrieval, grounding, and policy before integrating the latency-critical phone interface**. A fluent call that delivers an unsupported diagnosis is a failed product.

Rules:

- One milestone is active at a time.
- Each milestone is independently demoable and reversible.
- Exit gates are objective; unknown metrics fail the gate.
- Provider-specific code stays behind adapters.
- Paid/live tests are opt-in and budget-limited.
- No production mutation executor is built in the MVP.
- A blocked gate is fixed or explicitly waived by a human through an ADR; agents cannot waive it.

## 2. Milestone dependency graph

```text
W0 Contracts + lab
 ├─> W1 Signal/triage
 ├─> W2 Investigator
 └─> W3 Knowledge vault
       └─> W4 Grounding + policy
W1 + W2 + W3 + W4
 └─> W5 Durable orchestration
       └─> W6 Offline voice loop
             └─> W7 PSTN and telephony
                   └─> W8 Join the brains
                         └─> W9 Approval + dispatch
                               └─> W10 Reliability + escalation
                                     └─> W11 Evaluation + pilot hardening
```

## 3. Week 0 — Repository, contracts, and breakable lab

### Goal

Create a reproducible, safe development base and the ground-truth fault corpus.

### Deliverables

- Monorepo layout from `architecture.md`.
- Python 3.12 workspace, locked dependencies, standard scripts, and CI skeleton.
- Docker Compose for Postgres + pgvector, Redis or NATS, Temporal dev server, Prometheus, and `labs/broken-shop`.
- Pydantic contracts for alerts, incidents, evidence, hypotheses, runbook chunks, policy decisions, and Incident Context Object.
- Initial migrations for core lifecycle tables.
- Broken-shop: FastAPI checkout service, Postgres, Redis, deterministic seed data.
- Fault controls for:
  - Connection-pool exhaustion.
  - OOM/process death.
  - Database deadlock.
  - HTTP 5xx storm.
  - Slow query.
  - Network degradation through Toxiproxy.
- k6 load profiles and cleanup scripts.
- Canonical fixture manifest with expected cause, impact, evidence, and runbook eligibility.
- Safe defaults: fake telephony, deny-all mutation, no recording, no paid provider calls.

### Verification

- Fresh clone starts locally from one documented command.
- Every fault can be injected and reset without manual database repair.
- Contract JSON-schema snapshots are generated and checked.
- Migration upgrade/downgrade test passes on an empty and seeded database.
- CI runs format, lint, types, unit tests, secret scan, and schema checks.

### Exit gate

Six canonical failures are reproducible, observable, and paired with ground truth. No real external side effect is possible with default configuration.

## 4. Week 1 — Signal ingest, dedupe, and severity policy

### Goal

Turn noisy, retrying alerts into one trustworthy incident decision.

### Deliverables

- FastAPI gateway with health/readiness endpoints.
- Source-adapter interface plus initial Prometheus/Alertmanager and Sentry adapters.
- HMAC/signature and timestamp verification.
- Payload-size limits, replay protection, and encrypted raw-payload option.
- Versioned fingerprint implementation.
- Exact idempotency on source delivery ID.
- Configurable grouping window and flapping suppression.
- Deterministic severity/paging policy with `voice_page`, `message_only`, and `suppress` outcomes.
- Incident and alert persistence.
- Audit events and OpenTelemetry traces.

### Verification

- Invalid signature, stale timestamp, oversized body, replay, and malformed payload tests.
- Property-based tests for fingerprint stability and exclusion of volatile fields.
- Concurrent delivery test proves one alert row per delivery ID.
- Load fixture sends 50 related alerts and creates exactly one incident.
- Quiet-hours, maintenance-window, rate-cap, and severity policy tests.

### Exit gate

The canonical alert storm creates one incident and one workflow-start intent; duplicate deliveries do not create duplicate state.

## 5. Week 2 — Investigator and evidence model

### Goal

Produce a correct, compact analytical brief from bounded evidence before any voice work.

### Deliverables

- Investigator application with a hard 60-second deadline and per-tool timeouts.
- Typed ports for logs, metrics, traces, deployments, source diffs, database health, queue health, and past incidents.
- Deterministic fake adapters populated from broken-shop fixtures.
- Parallel evidence collection with size and time bounds.
- Evidence normalization, provenance, redaction, and injection-neutralization.
- Timeline builder and deploy/signal correlation.
- Hypothesis builder with supporting, contradicting, and missing evidence.
- Incident Context Object validation, persistence, and token-budget enforcement.
- Partial-result path for missing or failed sources.

### Verification

- Golden tests for all canonical faults.
- Tool timeout and partial-output tests.
- Source-ID integrity and dangling-reference rejection.
- Prompt-injection strings in logs remain inert data.
- Evaluation reports headline accuracy, impact accuracy, hypothesis rank, confidence calibration, and deadline.

### Exit gate

For all canonical faults, headline and impact are correct, evidence references resolve, no unsupported command appears, and a useful ICO is produced within 60 seconds.

## 6. Week 3 — Knowledge vault and hybrid retrieval

### Goal

Retrieve the right verified operational procedure and refuse undocumented failures.

### Deliverables

- Runbook source-adapter contract with local Markdown implementation first.
- Structure-aware parser preserving heading path, prerequisites, warnings, command, blast radius, rollback, owner, source, ACL metadata, and verification date.
- Postgres FTS and pgvector indexes.
- Embedding provider adapter with deterministic test embedding.
- Lexical and vector candidate retrieval.
- Reciprocal rank fusion and reranker adapter.
- Eligibility filter for stale, superseded, inaccessible, ownerless, or unverified chunks.
- Curated retrieval dataset including exact identifiers such as `OOMKilled` and `pg_stat_activity`.
- Retrieval report: recall@k, MRR, stale rejection, and refusal precision.

### Verification

- Chunk-boundary snapshots.
- Exact-token queries beat semantically related but incorrect procedures.
- RRF behavior is deterministic under fixed ranks.
- Stale and superseded chunks are excluded after retrieval, before answer generation.
- Undocumented fault returns no eligible procedure and triggers refusal.

### Exit gate

Recall@5 is at least 0.90, MRR is at least 0.80, all stale-runbook tests pass, and canonical undocumented faults produce no procedural answer.

## 7. Week 4 — Grounding validator and action policy

### Goal

Make unsupported speech and unapproved mutations structurally impossible.

### Deliverables

- Claim schema and classifier for `observed`, `retrieved`, and `inferred` statements.
- Response composer that carries claim references.
- Pre-output validator with deterministic refusal fallback.
- Canonical command model linked to one eligible runbook step.
- OPA/Rego policy bundle with Tier 1, Tier 2, and deny decisions.
- Unknown-operation default deny.
- Approval FSM implemented and tested independent of voice.
- Exact keyword matching: `GO` for initial approval; second exact confirmation for destructive/irreversible operations.
- Digest equality across proposed, read-back, signed, and dispatched command text.
- Signed approval-record contract and append-only audit-chain design.
- Deny-all mutation adapter.

### Verification

- Adversarial claim and command fixtures.
- Model text cannot change policy tier.
- “Yeah,” “do it,” keyword in unrelated speech, low-confidence STT, and replay do not approve.
- Editing one byte of a command invalidates prior approval.
- Audit failure prevents dispatch.
- Unsupported procedure always becomes the fixed refusal response.

### Exit gate

Zero unsupported commands and zero false approvals across the curated adversarial suite. The MVP path has no code path that executes Tier 2 actions.

## 8. Week 5 — Durable incident orchestration

### Goal

Own the entire incident lifecycle in a replay-safe workflow.

### Deliverables

- Temporal workflow with stable `incident/<id>` identity.
- Signals for additional alerts, acknowledgement, resolution, suppression, and cancellation.
- Activities for investigation, persistence, roster lookup, call preparation, and messaging.
- Investigation deadline and partial-brief branch.
- Retry policies and idempotency keys for every activity.
- Durable timers, escalation state, continue-as-new policy, and immutable audit events.
- Workflow query endpoints for console/status.

### Verification

- Replay test on captured histories.
- Duplicate start and signal tests.
- Kill worker during investigation; another worker resumes.
- Timeout and provider-failure tests preserve incident state.
- Activity retry does not duplicate an incident context or external intent.

### Exit gate

A worker can be killed at each nonterminal state without losing or duplicating the incident lifecycle.

## 9. Week 6 — Offline conversational loop

### Goal

Validate streaming conversation, interruption, concise speech, and latency without PSTN complexity.

### Deliverables

- LiveKit Agents worker in local/file or browser loopback mode.
- Provider interfaces for STT, conversation model, and TTS.
- Deepgram and Cartesia/Deepgram adapters behind feature flags; deterministic local fakes for CI.
- Silero VAD plus semantic endpointing.
- Streaming first-sentence validation and TTS.
- Barge-in cancellation.
- Two-sentence normal response policy and “let me check” asynchronous lookup behavior.
- Stage-level latency tracing.
- Synthetic audio suite with slow, drowsy, accented, interrupting, and skeptical personas.

### Verification

- No blocking network I/O on the audio loop.
- Barge-in stops playback within target.
- All speech passes grounding validation before emission.
- Tool calls exceeding 1.5 seconds use hold/fallback behavior.
- Local p50/p95 timing report is produced.

### Exit gate

Grounded offline conversations meet p50 ≤800 ms and p95 <1 second in the controlled environment, or a documented bottleneck and approved mitigation exists.

## 10. Week 7 — SIP and controlled telephony

### Goal

Make an allowlisted phone ring safely and measure real network/audio behavior.

### Deliverables

- LiveKit Cloud project and outbound SIP trunk adapter.
- Twilio Elastic SIP trunk configuration documentation.
- E.164 normalization, allowlist, live-test feature gate, and spend cap.
- Answering-machine detection and voicemail outcome handling.
- Recording announcement and recording-off default.
- Provider callback signature verification and idempotency.
- Region selection near SIP PoP.
- Text fallback when voice cannot connect.

### Verification

- Fake provider tests in CI.
- Explicitly authorized live test to an allowlisted number.
- Human, voicemail, no-answer, busy, provider-error, and callback-replay scenarios.
- Real p50/p95 latency, jitter, drop, and interruption measurements.
- Kill switch prevents every dial path.

### Exit gate

An authorized test phone receives a grounded hardcoded/fixture briefing; voicemail is not marked acknowledged; no unallowlisted destination can be dialed.

## 11. Week 8 — Integrate Investigator and Voice

### Goal

Deliver the precomputed brief and grounded follow-up answers over a real call.

### Deliverables

- ICO handoff from Temporal to voice worker.
- Compact voice prompt and structured context loader.
- Opening two-sentence briefing.
- Follow-up Q&A from ICO plus eligible runbook chunks.
- Narrow current-state lookup tools only.
- Transparent handling of partial investigation and stale context.
- Conversation transcript with claim/source annotations.
- Caller comprehension rubric.

### Verification

- End-to-end test for each canonical fault.
- Friend/operator comprehension test without prior system knowledge.
- No raw logs or oversized runbook content enters voice context.
- Every procedural statement includes an eligible chunk ID internally and verification date in speech when relevant.
- Latency gate holds after full integration.

### Exit gate

A caller can correctly identify what failed, impact, confidence, evidence, and whether a verified procedure exists, with no unsupported procedural speech.

## 12. Week 9 — Spoken approval, dispatch, and recovery watch

### Goal

Complete a human-gated, auditable remediation handoff without autonomous mutation.

### Deliverables

- Voice wiring for the approval FSM.
- Canonical command readout, blast radius, reversibility, and source.
- Exact `GO` capture and second confirmation where policy requires it.
- Caller authorization result in policy input.
- Signed approval and transcript-span persistence.
- Authorized SMS/Slack dispatch adapters.
- Human paste/execute acknowledgment path.
- Objective recovery monitors and on-call status updates.

### Verification

- Noisy and ambiguous approval audio suite.
- Call-drop at every approval step invalidates incomplete approval.
- Digest equality across all representations.
- Duplicate dispatch callbacks are idempotent.
- Audit write failure blocks dispatch.
- Recovery is based on metrics/health, not human assertion alone.

### Exit gate

Every dispatched Tier 2 snippet has a complete signed record, valid runbook source, authorized caller, exact transcript span, and matching digest. Nothing is executed by the system.

## 13. Week 10 — Escalation and night-survival hardening

### Goal

Ensure the responder survives failures and reaches the right human without causing an alert storm of its own.

### Deliverables

- Primary retry, secondary, escalation contact, and full-brief channel ladder.
- Per-incident/global call caps and global telephony kill switch.
- Severity and quiet-hours gates.
- Multi-provider or deterministic text fallback where justified.
- Responder health checks, dead-man's switch, backup/restore, and runbooks.
- Separate failure-domain deployment.
- Chaos scenarios for Temporal worker, database, cache, voice provider, STT, TTS, and policy outage.

### Verification

- `kill -9` during investigation, dialing, connected call, and escalation.
- Temporal replay and failover.
- Provider outage and network-partition tests.
- Rate limits prevent runaway calls.
- Postgres unavailable causes fail-closed approval behavior.
- Restore drill verifies incident and audit data.

### Exit gate

The escalation ladder completes correctly despite worker restarts and simulated provider failures, while call/spend caps and kill switches remain effective.

## 14. Week 11 — Evaluation, compliance, and controlled pilot

### Goal

Turn prototype behavior into measurable, governable production behavior.

### Deliverables

- Regression suite for incident analysis, retrieval, grounding, voice, approval, and escalation.
- Deterministic checks plus calibrated LLM-as-judge rubrics where deterministic scoring is insufficient.
- Langfuse or equivalent trace review with privacy controls.
- Recording-consent, retention, deletion, access, and export procedures.
- Threat model and security review.
- Load/cost tests and per-incident budget dashboard.
- Auto-drafted postmortem with human-review requirement.
- Runbook-gap report; no automatic verification/promotion.
- Pilot plan, rollback plan, owner rotation, and operational SLOs.

### Verification

- Full canonical suite and adversarial personas.
- Judge calibration against human-labeled samples.
- CI gates on grounding, unsupported commands, false approvals, retrieval, latency, and call caps.
- Data-retention deletion drill.
- Controlled staging game day with explicit human authorization.

### Exit gate

All release metrics in `project-overview.md` pass, compliance owners approve the configured policy, and rollback/game-day evidence is recorded.

## 15. Environment promotion gates

### Local → staging

- Core tests and evals pass.
- No default live side effects.
- Threat model covers new integrations.
- Migrations and rollback tested.

### Staging → controlled pilot

- Analytical, retrieval, grounding, approval, latency, and replay gates pass.
- Only allowlisted callers/destinations.
- Recording and retention policy configured.
- Kill switches and spend limits tested.
- On-call participants explicitly consent.

### Controlled pilot → production

- False-page and missed-page rates are acceptable over the pilot.
- Human comprehension and trust scores meet target.
- Security/compliance review complete.
- Responder operations, ownership, backup, and escalation are staffed.
- Direct mutation remains disabled unless separately designed and approved.

## 16. Cross-cutting work required every week

- Update `progress-tracker.md` with evidence, not impressions.
- Add failure-path and idempotency tests.
- Track latency and cost changes for any hot-path/provider change.
- Keep adapters replaceable and contracts versioned.
- Review logs/traces for secret and PII leakage.
- Convert architectural changes into ADRs.
- Keep broken-shop fixtures and golden outputs synchronized.

## 17. Post-MVP options

These require separate ADRs and safety reviews:

- Speech-to-speech experimental mode behind text/claim inspection.
- Direct Tier 2 execution for an allowlisted reversible command set.
- Multi-language voice support.
- Qdrant or another dedicated vector store after measured scale limits.
- Managed voice provider fallback such as Vapi or Retell.
- Multi-region active/active responder.
- Automated runbook-update proposals with mandatory owner review.