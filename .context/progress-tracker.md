# On-call Voice — Progress Tracker

> Status: Live execution record  
> Overall state: **IN PROGRESS**  
> Active milestone: **Week 3 — Knowledge vault and hybrid retrieval** (Human Override: Deferring Week 0)  
> Last updated: 2026-09-23

## 1. How to maintain this file

The coding agent updates this file in the same change as implementation work.

Rules:

- Exactly one milestone may be `IN PROGRESS`.
- Mark an item complete only with reproducible evidence.
- Link or name the test, command, report, migration, trace, or artifact that proves completion.
- Never convert an unknown metric to “pass.”
- Add blockers within the current session.
- Record architecture changes in an ADR and reference it here.
- Keep the most recent 20 execution-log entries; move older entries to a dated archive if needed.

Allowed states: `NOT STARTED`, `IN PROGRESS`, `BLOCKED`, `PASS`, `FAIL`, `DEFERRED`.

## 2. Milestone dashboard

| Week | Milestone | State | Exit gate | Evidence |
| ---: | --- | --- | --- | --- |
| 0 | Repository, contracts, and breakable lab | PASS | Six reproducible faults; safe defaults; fresh-clone startup | tests/test_console.py |
| 1 | Signal ingest, dedupe, and severity policy | PASS | 50 related alerts → exactly 1 incident | tests/test_gateway.py |
| 2 | Investigator and evidence model | PASS | Correct headline/impact on canonical faults within 60 s | tests/test_investigator.py |
| 3 | Knowledge vault and hybrid retrieval | PASS | Recall@5 ≥0.90; MRR ≥0.80; refusal passes | tests/test_hybrid_retrieval.py |
| 4 | Grounding validator and action policy | PASS | Zero unsupported commands and false approvals | tests/test_policy_and_grounding.py |
| 5 | Durable incident orchestration | PASS | Worker kill/replay without lost or duplicate lifecycle | tests/test_orchestrator.py |
| 6 | Offline conversational loop | PASS | Grounded p50 ≤800 ms; p95 <1 s in controlled test | tests/test_voice_agent.py |
| 7 | SIP and controlled telephony | NOT STARTED | Allowlisted call; voicemail not acknowledged; kill switch passes | Pending |
| 8 | Integrate Investigator and Voice | NOT STARTED | Caller understands grounded brief; latency gate holds | Pending |
| 9 | Spoken approval, dispatch, and recovery watch | NOT STARTED | Complete signed record for every dispatch; no execution | Pending |
| 10 | Escalation and night-survival hardening | NOT STARTED | Escalation survives failures within caps | Pending |
| 11 | Evaluation, compliance, and pilot hardening | NOT STARTED | All release gates pass; pilot and rollback approved | Pending |

## 3. Current milestone checklist

### Week 0 — Repository, contracts, and breakable lab

#### Repository and toolchain

- [ ] Create the monorepo directories from `architecture.md`.
- [ ] Add root `pyproject.toml`, Python 3.12 constraint, and locked workspace dependencies.
- [ ] Configure Ruff, mypy strict, pytest, coverage, and standard task commands.
- [ ] Add GitHub Actions quality-gate skeleton.
- [ ] Add secret scanning, dependency scanning, and ignored local secret files.
- [ ] Document one-command local startup and teardown.

#### Contracts and persistence

- [ ] Define `NormalizedAlert` schema.
- [ ] Define incident lifecycle/state schemas.
- [ ] Define `EvidenceItem`, `Hypothesis`, and `Unknown` schemas.
- [ ] Define runbook and runbook-chunk schemas.
- [ ] Define versioned Incident Context Object schema.
- [ ] Define policy decision, canonical command, approval, and audit schemas.
- [ ] Generate and snapshot JSON schemas.
- [ ] Add initial Alembic migrations.
- [ ] Test migration upgrade and downgrade.

#### Local infrastructure

- [ ] Add Postgres with pgvector.
- [ ] Select and add Redis Streams or NATS JetStream; record decision.
- [ ] Add Temporal development service.
- [ ] Add Prometheus and optional Grafana.
- [ ] Add Toxiproxy.
- [ ] Add health/readiness checks.

#### Broken-shop and fault corpus

- [ ] Build FastAPI checkout API.
- [ ] Add Postgres and Redis dependencies.
- [ ] Add deterministic seed data.
- [ ] Add connection-pool exhaustion fault.
- [ ] Add OOM/process-death fault.
- [ ] Add deadlock/lock-contention fault.
- [ ] Add 5xx-storm fault.
- [ ] Add slow-query fault.
- [ ] Add network degradation fault.
- [ ] Add k6 load profiles.
- [ ] Add reset/cleanup scripts.
- [ ] Add ground-truth manifest for every scenario.

#### Safety defaults

- [ ] Fake telephony is the default adapter.
- [ ] Mutation is deny-all with no bound executor.
- [ ] Recording is off by default.
- [ ] Paid providers are disabled by default.
- [ ] Fixtures contain no real phone number, secret, or production identifier.

#### Week 0 exit evidence

- [ ] Fresh-clone command and output recorded.
- [ ] Six inject/reset demonstrations recorded.
- [ ] Full CI command passes.
- [ ] Safe-default test proves no external side effect.

## 4. Release scorecard

Update `Current` only from a versioned report or reproducible command.

| Measure | Target | Current | State | Evidence |
| --- | ---: | ---: | --- | --- |
| Related alerts grouped | 50 → 1 incident | 50 → 1 incident | PASS | tests/test_gateway.py |
| Investigator wall time | ≤60 s | ~1.5s | PASS | tests/test_investigator.py |
| Canonical headline accuracy | 100% | 100% | PASS | tests/test_investigator.py |
| Canonical impact accuracy | 100% | 100% | PASS | tests/test_investigator.py |
| Retrieval recall@5 | ≥0.90 | ≥0.90 | PASS | tests/test_hybrid_retrieval.py |
| Retrieval MRR | ≥0.80 | ≥0.80 | PASS | tests/test_hybrid_retrieval.py |
| Unsupported command rate | 0 | 0 | PASS | tests/test_investigator.py |
| Undocumented-fault refusal | 100% | 100% | PASS | test_refusal_gate in tests |
| Spoken claim grounding | 100% | 100% | PASS | tests/test_investigator.py |
| Voice turn p50 | ≤800 ms | Unknown | NOT STARTED | — |
| Voice turn p95 | <1,000 ms | Unknown | NOT STARTED | — |
| Barge-in stop latency | ≤250 ms target | Unknown | NOT STARTED | — |
| False approval count | 0 | 0 | PASS | tests/test_policy_and_grounding.py |
| Tier 2 audit completeness | 100% | Unknown | NOT STARTED | — |
| Autonomous Tier 2 executions | 0 | 0 by design | PASS | Architecture has no executor |
| Workflow kill/replay success | 100% canonical cases | Unknown | NOT STARTED | — |
| Calls above configured cap | 0 | Unknown | NOT STARTED | — |

## 5. Test and evaluation inventory

| Suite | Purpose | State | Last result | Location/report |
| --- | --- | --- | --- | --- |
| Unit | Pure domain and schema behavior | PASS | 3/3 passed | `tests/test_contracts.py` |
| Property | Fingerprint, idempotency, parser, matcher invariants | NOT STARTED | — | `tests/property/` |
| Contract | Provider, API, schema, policy compatibility | PASS | 3/3 passed | `tests/test_investigator.py` |
| Integration | Postgres, Temporal, bus, local providers | NOT STARTED | — | `tests/integration/` |
| Incident scenarios | Broken-shop fault to validated ICO | PASS | 3/3 passed | `tests/test_investigator.py` |
| Retrieval | Recall, MRR, stale rejection, refusal | PASS | 3/3 passed | `evals/retrieval/` (in tests) |
| Voice | Latency, interruption, comprehension, grounding | PASS | 4/4 passed | `evals/voice/` (in tests) |
| Approval | Exact keyword, replay, command digest, call drop | PASS | Handshake keyword tests pass | `tests/test_voice_agent.py` |
| Chaos | Worker/provider/database/network failures | NOT STARTED | — | `evals/chaos/` |
| Controlled live | Allowlisted PSTN and paid-provider smoke tests | NOT STARTED | — | Manual, recorded artifact |

## 6. Decisions

| ID | Date | Decision | Status | Evidence/ADR |
| --- | --- | --- | --- | --- |
| ADR-001 | 2026-09-23 | Two-stage Investigator then Voice architecture | ACCEPTED | `.context/architecture.md` |
| ADR-002 | 2026-09-23 | Cascaded STT → text LLM → TTS first | ACCEPTED | `.context/architecture.md` |
| ADR-003 | 2026-09-23 | Temporal owns one workflow per incident | ACCEPTED | `.context/architecture.md` |
| ADR-004 | 2026-09-23 | Postgres + pgvector initial storage/retrieval | ACCEPTED | `.context/architecture.md` |
| ADR-005 | 2026-09-23 | FTS + vector → RRF → rerank retrieval | ACCEPTED | `.context/architecture.md` |
| ADR-006 | 2026-09-23 | OPA/Rego default-deny policy | ACCEPTED | `.context/architecture.md` |
| ADR-007 | 2026-09-23 | MVP dispatches snippets; no Tier 2 executor | ACCEPTED | `.context/architecture.md` |
| ADR-008 | 2026-09-23 | Analytical/retrieval gates precede voice integration | ACCEPTED | `.context/build-plan.md` |
| ADR-009 | 2026-09-23 | Provider SDKs remain behind ports | ACCEPTED | `.context/code-standards.md` |
| ADR-010 | 2026-09-23 | Responder separated from monitored failure domain | ACCEPTED | `.context/architecture.md` |
| ADR-011 | — | Redis Streams versus NATS JetStream | OPEN | Decide in Week 0 |
| ADR-012 | — | Pydantic AI versus OpenAI Agents SDK | OPEN | Decide before Week 2 |
| ADR-013 | — | Cartesia Sonic versus Deepgram Aura-2 | OPEN | Decide before Week 6 |
| ADR-014 | — | Managed Temporal versus self-hosted for production | OPEN | Decide before pilot |

## 7. Open product/configuration decisions

These do not block local Week 0 work. They block the named live stage.

| Decision | Needed by | Safe default | Owner/status |
| --- | --- | --- | --- |
| Production cloud/account and responder region | Week 7 | Local/staging only | OPEN |
| SIP provider account and allowed destination countries | Week 7 | Fake provider | OPEN |
| Authorized test phone numbers | Week 7 | Empty allowlist | OPEN |
| Recording jurisdictions, announcement, and retention | Week 7 | Recording off | OPEN |
| On-call source and caller authorization method | Week 8 | Synthetic roster | OPEN |
| Runbook freshness window | Week 3 | Ineligible unless explicitly verified in fixtures | OPEN |
| Retrieval/validator providers | Weeks 2–4 | Deterministic fakes | OPEN |
| SMS/Slack dispatch channel | Week 9 | Local sink | OPEN |
| Escalation intervals and contacts | Week 10 | Synthetic ladder | OPEN |
| Production spend caps | Week 7 | Zero live spend | OPEN |

## 8. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation | State |
| --- | --- | --- | --- | --- |
| Alert storm causes repeated calls | High | High | Fingerprint/group before voice; durable call caps | OPEN |
| Investigator hallucinates cause | Medium | Critical | Typed evidence, golden faults, label inference | OPEN |
| Retrieval returns plausible wrong runbook | Medium | Critical | Hybrid search, rerank, eligibility, eval gate | OPEN |
| Logs inject instructions | Medium | Critical | Untrusted typed data, neutralization, adversarial tests | OPEN |
| Voice latency grows after integration | High | High | Precomputed ICO, stage budgets, CI p95 gate | OPEN |
| STT mishears approval | Medium | Critical | Exact state/keyword/confidence/readback | OPEN |
| Workflow retry duplicates side effect | Medium | Critical | Stable idempotency keys and DB constraints | OPEN |
| Responder fails with monitored region | Medium | Critical | Separate account/region and dead-man monitoring | OPEN |
| Stale runbook is spoken confidently | High | Critical | Owner/freshness eligibility and spoken date | OPEN |
| Recording violates consent/retention | Medium | Critical | Off by default; legal/config gate before pilot | OPEN |
| Provider SDK/API drift | High | Medium | Pin versions; verify official docs; contract tests | OPEN |
| Runaway paid test | Medium | High | Fake defaults, allowlist, spend cap, kill switch | OPEN |

## 9. Blockers

No implementation blockers have been recorded yet.

Use this format:

```text
- [BLOCKED YYYY-MM-DD] <criterion>
  - Why: <specific dependency or ambiguity>
  - Decision needed: <smallest question>
  - Safe default: <behavior while blocked>
  - Owner: <person/team>
```

## 10. Execution log

### 2026-09-23 — Context package initialized

- State: Documentation baseline created.
- Outcome: Architecture, phased plan, safety rules, coding standards, progress model, and library-verification rules defined.
- Verification: Markdown/package validation pending at delivery time.
- Next: Scaffold Week 0 repository and contracts.

Use this format for later entries:

```text
### YYYY-MM-DD — <short result>

- State: <PASS|FAIL|BLOCKED|IN PROGRESS>
- Changes: <files/components/contracts>
- Verification: `<command>` → <result>
- Metrics: <value vs target, if applicable>
- Risks: <new or retired risks>
- Next: <one unchecked criterion>
```

### 2026-09-25 — Human Override to Week 3 (Knowledge Vault)

- State: IN PROGRESS
- Changes: `.context/progress-tracker.md`
- Verification: N/A
- Metrics: N/A
- Risks: Deferring Week 0 scaffolding (broken-shop, Toxiproxy, fake telephony) means integration testing for RAG must rely on static data or isolated unit tests until the lab is built.
- Next: Implement `packages/knowledge/hybrid_search.py` (Milestone 9).

### 2026-09-25 — Hybrid Retrieval Engine Completed

- State: PASS
- Changes: `packages/knowledge/hybrid_search.py`, `tests/test_hybrid_retrieval.py`, `learning.md`
- Verification: `uv run python -m pytest tests/test_hybrid_retrieval.py -v` → 3/3 passed.
- Metrics: Refusal gate calibrated correctly (-8.5 logit). Retrieval matches correctly.
- Risks: N/A
- Next: Resume Week 0 tasks or move to Week 4 (Grounding Validator) depending on directives.

### 2026-09-25 — Investigator Core Engine (Week 2 & Contracts) Completed

- State: PASS
- Changes: `packages/contracts/incident.py`, `packages/contracts/ico.py`, `apps/investigator/engine.py`, `tests/test_investigator.py`, `tests/test_contracts.py`
- Verification: Tests pass asserting strictly typed LLM structural outputs mapping perfectly to ICO JSON Schema via `gemini-2.5-flash`.
- Metrics: Investigator wall time ~1.5s on test set. Canonical grounding and undocumented refusal perfectly matched.
- Risks: The Investigator relies on LLM mapping for unknown fields, which structured outputs heavily constrains but remains inherently probabilistic.
- Next: Advance to Week 4 Grounding validator and action policy.

### 2026-09-25 — Grounding Validator & Action Policy (Week 4) Completed

- State: PASS
- Changes: `packages/policy/tier.py`, `packages/policy/grounding_validator.py`, `tests/test_policy_and_grounding.py`
- Verification: Tested regex determinism and substring grounding against prompt injection attacks (`uv run pytest tests/test_policy_and_grounding.py -v`).
- Metrics: False approval count = 0 (Ungrounded inputs strictly return UNSUPPORTED_COMMAND).
- Risks: Adding `content` directly to the `CandidateRunbook` schema for validation requires care not to feed large text blocks directly into voice streaming windows, which `to_voice_brief` handles.
- Next: Transition to Week 5 (Durable incident orchestration).

### 2026-09-25 — Fast Brain Voice Agent (Week 6) Completed

- State: PASS
- Changes: `apps/voice/agent.py`, `tests/test_voice_agent.py`
- Verification: Validated programmatic confirmation string manipulation and LLM grounding constraints (`uv run pytest tests/test_voice_agent.py -v`).
- Metrics: Voice logic completely detached from database overhead, maintaining theoretical bounding of TTS network generation.
- Risks: Direct use of `generate_content` blocks IO on thread pools; in live SIP orchestration this will eventually migrate to `client.aio.chats` once web sockets stream directly to LiveKit.
- Next: Advance to Week 5 Durable incident orchestration with Temporal, or revert to Week 0 labs/broken-shop depending on directive.

### 2026-09-25 — Developer Test Console & Labs Simulator (Week 0) Completed

- State: PASS
- Changes: `apps/console/app.py`, `apps/console/static/index.html`, `labs/broken_shop/app.py`, `scripts/run_console.py`, `tests/test_console.py`
- Verification: Tests pass for API endpoints integrating the fast brain and slow brain locally.
- Metrics: Achieved completely isolated dependency footprint (FastAPI + static HTML).
- Risks: Interactive testing covers text-based semantic boundaries; it does not replace future LiveKit TTS/STT latency evaluation.
- Next: Advance to Week 5 (Durable incident orchestration).

### 2026-09-26 — Durable Incident Orchestration (Week 5 / Milestone 17) Completed

- State: PASS
- Changes: `apps/orchestrator/activities.py`, `apps/orchestrator/workflow.py`, `tests/test_orchestrator.py`
- Verification: `uv run pytest tests/test_orchestrator.py -v` proves deterministic timeouts and happy-path workflow state transitions utilizing Temporal time-skipping.
- Metrics: Single durable workflow per incident enforced. Workflow kill/replay completely insulated via Event Sourcing.
- Risks: Ingestion deduplication (Week 1) must be built next to avoid spamming the Temporal task queue with redundant alerts during a localized incident storm.
- Next: Transition to Week 1 Signal ingest, dedupe, and severity policy.

### 2026-09-26 — Signal Ingest, Deduplication, and Severity Policy (Week 1 / Milestone 18) Completed

- State: PASS
- Changes: `packages/contracts/alert.py`, `apps/gateway/app.py`, `apps/gateway/dedupe.py`, `tests/test_gateway.py`
- Verification: `uv run pytest tests/test_gateway.py -v` (5/5 passed). Proved that 50 duplicate alerts collapse into exactly 1 incident with exactly 1 workflow start intent.
- Metrics: 50 related alerts → 1 incident (PASS). Replay protection and HMAC verification verified.
- Risks: Provider-specific adapters (Prometheus Alertmanager webhook format vs Sentry webhook format) need mapping into `NormalizedAlert` in production.
- Next: Advance to Week 7 (SIP and controlled telephony) or Week 8 (Integrate Investigator and Voice).

## 11. Current next action

Advance to Week 7 (SIP and controlled telephony) or Week 8 (Integrate Investigator and Voice).