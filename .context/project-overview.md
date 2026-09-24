# On-call Voice — Project Overview

> Status: Product and engineering source of truth  
> Last updated: 2026-09-23

## 1. Mission

Build a system that detects a production failure, groups noisy alerts into one incident, investigates the failure in under 60 seconds, calls the on-call engineer, explains the best-supported root-cause hypothesis in plain speech, answers follow-up questions using only verified evidence and runbooks, and requires an explicit spoken approval before any mutating response is possible.

The system is a safety aid for human operators. It is not an autonomous production operator.

## 2. Product promise

When a high-severity incident occurs, the engineer should receive a call that opens with a useful two-sentence briefing instead of waiting while an AI explores the system.

The experience must answer five questions quickly:

1. What broke?
2. Who or what is affected?
3. What evidence supports that conclusion?
4. What verified procedure, if any, applies?
5. What is safe to do next, and what requires explicit approval?

## 3. The central architecture: two brains on two clocks

### Investigator — slow brain

- Runs before the phone rings.
- Has a 30–60 second wall-clock budget.
- Uses a frontier reasoning model through typed tools.
- Reads bounded logs, metrics, traces, deploys, runbooks, and similar incidents.
- Produces a validated, compact Incident Context Object.
- May return a partial brief when evidence or providers are unavailable.

### Voice Agent — fast brain

- Runs during the call.
- Targets 300–800 ms per conversational turn and p95 below 1 second.
- Uses a fast text model in a cascaded STT → LLM → TTS pipeline for the first production version.
- Speaks from precomputed context and performs only narrow, bounded lookups.
- Validates every response before audio is emitted.
- Uses a deterministic finite-state machine for consent and approval.

### Governing rule

Nothing expected to take longer than 1.5 seconds belongs in the normal conversational hot path. A slower lookup must be moved to pre-call investigation or run asynchronously behind an explicit spoken hold message.

## 4. Target users and operators

### Primary user

An on-call engineer who may be asleep, interrupted, on a noisy phone line, unfamiliar with the failing component, or operating under severe time pressure.

### Secondary users

- Incident commanders reviewing evidence and escalation status.
- Service owners maintaining runbooks and verification dates.
- Security and compliance reviewers auditing approvals, recordings, and data retention.
- Platform engineers operating the responder and provider integrations.
- Engineering leaders reviewing reliability, false-page rate, and runbook gaps.

## 5. Core user journey

1. A monitor sends a signed alert webhook.
2. Ingest verifies the signature and idempotency key.
3. Triage fingerprints, deduplicates, groups, scores severity, and chooses voice, message-only, or suppress.
4. One durable workflow is created or signaled for the incident.
5. The Investigator gathers bounded evidence in parallel and retrieves verified runbook chunks.
6. A strict schema validates the Incident Context Object.
7. If policy requires a call, the workflow dials the primary on-call contact.
8. The Voice Agent announces recording when enabled, verifies it reached a person, and delivers a concise briefing.
9. Follow-up answers are limited to observed evidence, eligible runbook text, and clearly labeled inference.
10. Read-only lookups may run automatically within latency and policy limits.
11. Any proposed mutation is blocked. The agent reads the canonical command, blast radius, reversibility, and source aloud.
12. Only an exact spoken `GO` in the expected state counts as initial approval. Destructive or irreversible operations require a second exact confirmation after verbatim readback.
13. In the MVP, the approved snippet is sent through an authorized text channel for a human to paste; the agent never runs it.
14. The system watches objective recovery signals and reports status.
15. Artifacts feed the incident timeline, postmortem draft, retrieval corpus, and runbook-gap report.

## 6. Scope

### In scope for the first production-capable release

- HMAC-verified alert ingestion.
- Idempotency, fingerprinting, deduplication, grouping, severity scoring, suppression, and rate limits.
- A deterministic broken-service lab with injectable failure modes.
- Typed read-only adapters for logs, metrics, traces, deploy history, source diffs, and service metadata.
- Investigator with a hard deadline and partial-result behavior.
- Structure-aware runbook ingestion and hybrid retrieval.
- Runbook ownership and verification-date enforcement.
- Evidence-linked hypotheses and claim-level grounding.
- Cascaded voice pipeline with streaming, semantic turn detection, VAD, barge-in, and noise handling.
- Outbound SIP calling, answering-machine detection, retry, and escalation.
- Deterministic dialog and approval state machines.
- Human-gated command dispatch, signed audit records, transcript spans, and recovery monitoring.
- Durable orchestration, immutable lifecycle events, observability, evaluation, kill switches, and spend caps.
- Recording announcement, configurable retention, and PII redaction.

### Deferred or optional

- Direct execution of mutating commands.
- Speech-to-speech production mode.
- Unbounded autonomous diagnosis.
- General-purpose infrastructure chat.
- Fully automatic incident resolution.
- Customer-facing calling.
- Multi-language production support.
- Kubernetes deployment when a simpler isolated container platform is sufficient.
- A custom vector database before the runbook corpus requires it.

## 7. Non-goals

The system will not:

- Replace the on-call engineer or incident commander.
- Claim certainty when it has only a hypothesis.
- Invent remediation steps from general model knowledge.
- Treat stale, unowned, or unverified runbook content as an executable procedure.
- Execute a Tier 2 action in the MVP.
- Make a real call during CI.
- Keep the only copy of incident state in a process, cache, or model context.
- Depend on the monitored production region for its own survival.

## 8. Grounding contract

Every external statement is one of three types:

| Class | Required source | Spoken behavior |
| --- | --- | --- |
| Observed | Raw telemetry or immutable incident facts with source ID and timestamp | State as an observation and include time/scale when useful. |
| Retrieved | Eligible runbook chunk with chunk ID, owner, and verification date | Name the runbook and surface how recently it was verified. |
| Inferred | Model reasoning grounded in cited observations/retrieval | Qualify as a best guess or hypothesis and include confidence when useful. |

If no verified procedure clears the retrieval threshold, the permitted response is: explain what was observed, explicitly say that no verified procedure is available, and optionally identify the closest related runbook without presenting it as instruction.

## 9. Safety model

### Tier 1 — read-only

Examples: query logs, fetch metrics, describe a pod, list recent deploys, read configuration, inspect status.

These may auto-run when:

- The policy engine classifies the exact tool operation as read-only.
- Input schemas, scope, timeout, and result limits are enforced.
- The operation is logged and cannot mutate through a hidden side effect.

### Tier 2 — mutating

Examples: restart, rollback, scale, edit configuration, flush cache, run migration, change traffic, modify data, or invoke any tool without a proven read-only contract.

Rules:

- Default deny.
- Deterministic policy classification; never model judgment.
- Procedure must map to an eligible runbook chunk and canonical command.
- Agent reads command, blast radius, reversibility, and source.
- Exact spoken approval is required in the correct FSM state.
- Destructive or irreversible work requires a second exact approval after readback.
- Signed audit record precedes dispatch.
- MVP dispatches for human execution and does not execute.

## 10. Success metrics and release gates

| Area | Metric | Target |
| --- | --- | --- |
| Detection | Valid high-severity alert accepted | 99.9% excluding upstream outage |
| Dedupe | 50 alerts from one injected outage | Exactly 1 incident |
| Investigation | Useful Incident Context Object | ≤60 s wall clock |
| Investigation quality | Correct headline and impact on five canonical faults | 100% |
| Grounding | Spoken operational claims with valid source classification | 100% |
| Unsupported command rate | Commands not present in eligible runbook | 0 |
| Refusal | Undocumented fault correctly refused | 100% of canonical tests |
| Retrieval | Recall@5 on curated runbook queries | ≥0.90 before voice integration |
| Retrieval | MRR on curated runbook queries | ≥0.80 before voice integration |
| Voice | End-to-end perceived turn latency | p50 ≤800 ms; p95 <1 s |
| Interruption | Barge-in stops playback | ≤250 ms target |
| Approval | Tier 2 records with transcript span and source ID | 100% |
| Mutation safety | Unapproved or autonomous Tier 2 execution in MVP | 0 |
| Durability | Worker killed during incident | Workflow resumes/escalates correctly |
| Paging hygiene | Calls above per-incident/global cap | 0 |
| Audit | Incident transitions represented by durable events | 100% |

Targets are gates, not aspirations. A phase cannot be declared complete when its gate is unknown.

## 11. Canonical fault scenarios

`labs/broken-shop` must reproducibly inject at least:

1. PostgreSQL connection-pool exhaustion.
2. Container or process out-of-memory failure.
3. Database deadlock or lock contention.
4. HTTP 5xx storm.
5. Slow query or latency saturation.
6. Redis/network degradation through Toxiproxy.

Each scenario needs:

- Trigger and cleanup scripts.
- Expected signal timeline.
- Ground-truth root cause.
- Expected impact statement.
- Eligible and ineligible runbook chunks.
- Expected investigator evidence.
- Expected refusal/approval behavior.

## 12. Data and privacy classification

| Data | Classification | Handling |
| --- | --- | --- |
| Secrets, tokens, signing keys | Restricted | Secret manager only; never logs/prompts/repo. |
| Phone numbers, caller identity | Sensitive personal data | Encrypt, mask, minimize, restrict access. |
| Recordings and transcripts | Sensitive operational/personal data | Consent, encryption, access control, retention policy. |
| Raw logs/traces | Sensitive operational data | Bound, redact, delimit as untrusted input. |
| Runbooks | Internal operational data | Preserve ACL/source/owner/verification metadata. |
| Incident Context Object | Internal sensitive | Encrypt, version, audit, avoid excess raw payload. |
| Audit signatures | Integrity-critical | Append-only storage and key rotation. |
| Synthetic lab fixtures | Test data | Must not contain real secrets or personal data. |

## 13. Key product principles

- **Brief first, conversation second.** Thinking happens before dialing.
- **Evidence over fluency.** A concise refusal is better than a plausible invention.
- **Determinism around danger.** Policy and approval are state machines, not prompts.
- **Fail visibly and safely.** Partial, stale, missing, or low-confidence evidence is named.
- **Human execution by default.** Approval does not imply autonomous execution.
- **Measure the experience.** Latency, grounding, retrieval, interruption, and false pages are release metrics.
- **Build a system that can be broken on purpose.** The failure lab and eval corpus are product infrastructure.

## 14. Domain glossary

- **Alert:** A single signal emitted by a monitoring source.
- **Fingerprint:** Stable key identifying alerts that likely represent the same failure.
- **Incident:** Grouped operational event with one lifecycle and workflow.
- **Incident Context Object (ICO):** Compact validated brief passed from Investigator to Voice Agent.
- **Evidence item:** Bounded observation with source ID, timestamp, provenance, and redaction status.
- **Runbook chunk:** One retrieval unit preserving procedure, heading path, owner, source, and verification date.
- **Eligible runbook:** Owned, within verification freshness policy, accessible to the caller, and not superseded.
- **Grounding:** Linking a claim to observed or retrieved evidence and labeling inference.
- **Tier 1:** Proven read-only operation.
- **Tier 2:** Mutating, potentially mutating, or unclassified operation.
- **Approval handshake:** Deterministic sequence of proposal, readback, exact keyword, and optional second confirmation.
- **Barge-in:** Caller interruption that immediately stops agent speech and returns to listening.
- **AMD:** Answering-machine detection.
- **RRF:** Reciprocal rank fusion used to combine lexical and vector retrieval ranks.
- **Failure domain:** Infrastructure whose simultaneous loss should not disable both product and responder.

## 15. Assumptions requiring environment configuration

The repository must not hard-code:

- Provider accounts, credentials, phone numbers, or on-call rosters.
- Recording mode, consent text, retention period, or residency region.
- Severity thresholds or quiet hours.
- Runbook verification freshness window.
- Retrieval confidence thresholds.
- Escalation intervals and contact ladder.
- Maximum calls, per-incident spend, or global spend.
- Live mutation capability.

Safe defaults are: no real calls, recording off, mutation deny-all, message sinks local, and all paid integrations mocked.

## 16. Completion horizon

The project is production-capable only after:

- Analytical and retrieval gates pass before voice integration.
- The voice path passes latency, barge-in, and grounding validation.
- Approval records are complete and no Tier 2 execution exists in the MVP.
- Kill/replay/escalation tests pass.
- A controlled pilot validates consent, paging hygiene, and operator comprehension.
- Operations, rollback, incident response for the responder, and ownership are documented.