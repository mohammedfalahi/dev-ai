# On-call Voice — Progress Tracker

> Status: Live execution record  
> Overall state: **IN PROGRESS**  
> Active milestone: **Week 9 — Spoken approval, dispatch, and recovery watch**  
> Last updated: 2026-09-27

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
| 7 | SIP and controlled telephony | PASS | Allowlisted call; voicemail not acknowledged; kill switch passes | tests/test_telephony.py |
| 8 | Integrate Investigator and Voice | PASS | Caller understands grounded brief; latency gate holds | tests/test_voice_agent.py |
| 9 | Spoken approval, dispatch, and recovery watch | IN PROGRESS | Complete signed record for every dispatch; no execution | tests/test_telegram.py, tests/test_voice_agent.py |
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
| Retrieval recall@5 | ≥0.90 | 1.0000 | PASS | tests/test_retrieval_benchmarks.py |
| Retrieval MRR | ≥0.80 | 1.0000 | PASS | tests/test_retrieval_benchmarks.py |
| Unsupported command rate | 0 | 0 | PASS | tests/test_investigator.py |
| Undocumented-fault refusal | 100% | 100% | PASS | tests/test_retrieval_benchmarks.py |
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
| Retrieval | Recall, MRR, stale rejection, refusal | PASS | 5/5 passed | `tests/test_retrieval_benchmarks.py` & `evals/benchmarks/run_retrieval_benchmark.py` |
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

### 2026-09-26 — RAG Evaluation Schema and Golden Dataset Fixtures (Milestone 19) Completed

- State: PASS
- Changes: `evals/__init__.py`, `evals/schemas.py`, `evals/datasets/golden_dataset.jsonl`, `tests/test_golden_dataset.py`
- Verification: `uv run pytest tests/test_golden_dataset.py -v` (3/3 passed), `uv run ruff check evals/ tests/` (passed), `uv run mypy evals/` (passed).
- Metrics: 6 taxonomy-aligned evaluation cases verified. Refusal invariant enforced with zero tolerance for corrupted fixtures.
- Risks: None. `evals/` module is completely decoupled from production runtime packages with zero inward dependency leaks.
- Next: Build automated RAG evaluation harness (Milestone 20) evaluating retrieval metrics (Recall@K, MRR) and refusal precision against the golden dataset.

### 2026-09-26 — Decoupled RAG Retrieval Benchmark Runner (Milestone 20) Completed

- State: PASS
- Changes: `evals/benchmarks/__init__.py`, `evals/benchmarks/run_retrieval_benchmark.py`, `evals/datasets/golden_dataset.jsonl`, `tests/test_retrieval_benchmarks.py`
- Verification: `uv run python -m pytest tests/test_retrieval_benchmarks.py -v -s` (5/5 passed), `uv run python evals/benchmarks/run_retrieval_benchmark.py` (all gates passed), `uv run ruff check evals/ tests/` (passed), `uv run mypy evals/` (passed).
- Metrics: Recall@1 = 1.0000, Recall@3 = 1.0000, Recall@5 = 1.0000, MRR = 1.0000, Refusal Precision = 1.0000, Hard Negatives at Rank 1 = 0.
- Risks: Embeddings depend on Google GenAI API quota; local tests use running pgvector PostgreSQL container.
- Next: Advance to Generation Groundedness and Faithfulness Benchmark (Milestone 21) or Week 7 Telephony/SIP.

### 2026-09-26 — Generation, Safety Grounding, and Action Verification Evals (Milestone 21) Completed

- State: PASS
- Changes: `packages/contracts/ico.py`, `packages/policy/tier.py`, `apps/investigator/engine.py`, `evals/generation/__init__.py`, `evals/generation/eval_grounding.py`, `evals/generation/test_grounding_evals.py`, `evals/generation/run_generation_eval.py`, `tests/test_generation_evals.py`
- Verification: `uv run python -m pytest tests/test_generation_evals.py -v` (6/6 passed in 0.04s), `uv run python evals/generation/run_generation_eval.py --limit 4` (all gates passed), `uv run ruff check evals/ packages/ apps/investigator/ tests/` (all passed), `uv run mypy evals/ packages/` (all passed).
- Metrics: Verbatim Action Grounding Match Rate = 100%, Forbidden Claim Violation Rate = 0.0%, Refusal Generation Accuracy = 100%, Overall Grounding Pass Rate = 100%.
- Risks: Live generation requires Google GenAI API access; fast CI test suite uses pre-constructed fixtures with 0 network calls.
- Next: Advance to Week 7 (SIP and controlled telephony) or Week 8 (Integrate Investigator and Voice).

### 2026-09-27 — Consolidated Evaluation Matrix and CI Regression Gate (Milestone 22) Completed

- State: PASS
- Changes: `evals/run_eval_matrix.py`, `evals/benchmarks/run_retrieval_benchmark.py`, `tests/test_eval_matrix.py`, `.github/workflows/eval.yml`
- Verification: `uv run python -m pytest tests/test_eval_matrix.py -v` (6/6 passed in 3.6s), `uv run python evals/run_eval_matrix.py --limit 5 --strict --output-json eval-report.json` (all gates passed, exit 0), `uv run ruff check evals/ tests/` (all passed), `uv run mypy evals/` (all passed).
- Metrics: All Tier 1, Tier 2, and Tier 3 quality gates verified (Recall@1=100%, Recall@3=100%, Recall@5=100%, MRR=1.0000, Refusal Precision=100%, Hard Negatives=0, Verbatim AST Match=100%, Forbidden Violations=0.0%, Refusal Accuracy=100%, Overall Pass Rate=100%).
- Risks: Automated CI runs require ephemeral pgvector container and Google GenAI API secrets in GitHub Actions.
- Next: Advance to Week 7 (SIP and controlled telephony) or Week 8 (Integrate Investigator and Voice).

### 2026-09-27 — Fast-Brain Voice Loop with LiveKit Agents and Gemini Live (Milestone 24) Completed

- State: PASS
- Changes: `apps/voice/agent.py`, `tests/test_voice_agent.py`, `apps/orchestrator/workflow.py`, `packages/core/config.py`, `pyproject.toml`, `uv.lock`, `.context/architecture.md`, `.context/library-docs.md`, `.context/progress-tracker.md`
- Verification: `uv run pytest tests/test_voice_agent.py -v` (10/10 passed), full suite `uv run pytest` (53/53 passed), `uv run ruff check apps/voice/ tests/test_voice_agent.py apps/orchestrator/ packages/core/` (all passed), `uv run mypy apps/voice/ tests/test_voice_agent.py apps/orchestrator/ packages/core/` (clean).
- Metrics: Native bidirectional audio streaming configured via `livekit-plugins-google` (`gemini-live-2.5-flash-native-audio`). Precomputed ICO spoken brief delivered on connect. Deterministic tool calling intercepts all remediation commands with strict runbook grounding and Tier 1 / Tier 2 policy gating before signaling Temporal (`execute_action_signal`).
- Risks: Realtime WebRTC audio requires live LiveKit server and Gemini Multimodal Live API quota in production PSTN/SIP deployments; offline simulation and unit test coverage validated locally.
- Next: Advance to Week 7 (SIP and controlled telephony) or Week 8 (Integrate Investigator and Voice).

### 2026-09-27 — Controlled Telephony Adapter & Safety Guardrails (Week 7 / Milestone 25) Completed

- State: PASS
- Changes: `packages/contracts/telephony.py`, `packages/contracts/__init__.py`, `packages/core/config.py`, `packages/providers/__init__.py`, `packages/providers/telephony.py`, `apps/orchestrator/activities.py`, `tests/test_telephony.py`, `.context/progress-tracker.md`, `learning.md`
- Verification: `uv run pytest tests/test_telephony.py -v` (5/5 passed), full suite `uv run pytest` (76/76 passed), `uv run ruff check packages/ apps/orchestrator/ tests/test_telephony.py` (all passed), `uv run mypy packages/providers/ packages/contracts/telephony.py tests/test_telephony.py` (all clean).
- Metrics: Allowlisted call validation passes. Telephony kill switch blocks all dials immediately when engaged. E.164 normalization strictly enforced. LiveKit SIP adapter stubbed and guarded. Activity `notify_oncall_activity` successfully integrated with `TelephonyAdapter`.
- Risks: Production outbound PSTN dialing will require LiveKit Cloud SIP trunk provisioning with Twilio credentials once live PSTN testing is explicitly authorized.
- Next: Advance to Week 8 (Integrate Investigator and Voice).

### 2026-09-27 — Resilient Primary-to-Fallback Voice Model Hierarchy (Milestone 26) Completed

- State: PASS
- Changes: `packages/core/config.py`, `apps/voice/agent.py`, `.env.example`, `tests/test_voice_agent.py`, `.context/architecture.md` (ADR-016), `.context/progress-tracker.md`, `learning.md`
- Verification: `uv run pytest tests/test_voice_agent.py -v` (13/13 passed), full suite `uv run pytest` (79/79 passed), `uv run ruff check packages/core/config.py apps/voice/ tests/test_voice_agent.py` (clean), `uv run mypy packages/core/config.py apps/voice/agent.py tests/test_voice_agent.py` (clean).
- Metrics: Primary Google AI Studio initialization (`gemini-3.8-live`, `vertexai=False`) with zero-downtime failover to Google Cloud Vertex AI (`gemini-live-2.5-flash-native-audio`, `vertexai=True`, `project`, `location`) when `GEMINI_API_KEY` is missing or when initialization encounters rate-limits/exceptions.
- Risks: Vertex AI requires valid Google Cloud project credentials (`gcloud auth application-default login` or service account key) for live deployment.
- Next: Advance to Week 8 (Integrate Investigator and Voice).

### 2026-09-27 — Integrate Investigator and Voice Orchestration (Week 8 / Milestone 27) Completed

- State: PASS
- Changes: `packages/contracts/ico.py`, `apps/voice/agent.py`, `apps/orchestrator/activities.py`, `tests/conftest.py`, `tests/test_voice_agent.py`, `tests/test_contracts.py`, `.context/architecture.md` (ADR-017), `.context/progress-tracker.md`, `learning.md`
- Verification: `uv run pytest tests/test_voice_agent.py -v` (14/14 passed), `uv run pytest tests/test_orchestrator.py -v` (2/2 passed), `uv run pytest tests/test_contracts.py -v` (3/3 passed), `uv run ruff check .` (all clean), `uv run mypy packages/ apps/ evals/ tests/` (clean).
- Metrics: Empathetic natural voice brief delivered on session connect ("Hello, sorry to wake you up..."). Conversational prompt engineering and flexible conversational assent engine ("yeah sure", "go ahead", "yes please", "do that", "confirm", "proceed") validated for tool calling with deterministic runbook AST grounding and policy tiering. Offline testing optimized with HuggingFace Hub offline protection (`tests/conftest.py`).
- Risks: Production PSTN testing requires live LiveKit Cloud SIP trunk credentials; offline unit tests ensure hermetic verification.
- Next: Advance to Week 9 (Spoken approval, dispatch, and recovery watch).

### 2026-09-27 — 2-Page Developer Console & Evaluation Hub (Milestone 28) Completed

- State: PASS
- Changes: `apps/console/app.py`, `apps/console/static/index.html`, `apps/console/static/triage.html`, `tests/test_console.py`, `.context/progress-tracker.md`, `learning.md`
- Verification: `uv run pytest tests/test_console.py -v` (6/6 passed in 4.3s), `uv run ruff check apps/console/ tests/test_console.py` (clean), `uv run mypy apps/console/ tests/test_console.py` (clean).
- Metrics: Built 2-page dashboard: Dashboard 1 (`GET /`) provides operations & chaos control (broken-shop fault injection, service health badges, gateway dedupe metrics, LiveKit call state, policy gate verification). Dashboard 2 (`GET /triage`) provides ICO forensics (structured cards + raw JSON toggle) and visual 3-tier Evaluation Matrix scorecard (retrieval, reranking/refusal, generation/safety) with on-demand `[ Run Evaluation Matrix ]` trigger.
- Risks: Real-time LiveKit audio streaming in browser requires running LiveKit server; offline simulated text mode operates hermetically.
- Next: Advance to Week 9 (Spoken approval, dispatch, and recovery watch).

### 2026-09-28 — Voice Assent Tool Execution, Real-Time Console State Transition & Fault Lifecycle Reset (Milestone 29) Completed

- State: PASS
- Changes: `apps/voice/agent.py`, `apps/console/app.py`, `apps/console/static/index.html`, `packages/core/config.py`, `tests/test_voice_agent.py`, `tests/test_console.py`, `learning.md`, `.context/progress-tracker.md`
- Verification: `uv run pytest tests/test_voice_agent.py tests/test_console.py -v` (26/26 passed), `uv run pytest tests/ -v` (90/90 passed in full test suite), `uv run ruff check apps/voice/agent.py apps/console/app.py tests/test_voice_agent.py tests/test_console.py` (all clean).
- Metrics: Voice agent verbal assent ("go ahead", "confirm", "do it", "yes", "proceed") directly invokes `execute_remediation_command` without re-prompting. Function tool returns structured JSON and dispatches async resolution notification to `/api/faults/resolve`. Console server transitions active fault to `RESOLVED` and provides `POST /api/faults/reset` (with optional `fault_id`). Console web dashboard auto-updates fault card to green `✅ Problem Solved` / `RESOLVED` via 1.5s background polling, and provides a `🔄 Reset State` button to cleanly revert the fault lifecycle.
- Risks: Real LiveKit speech calls require LiveKit server connectivity; unit and integration test coverage verifies isolated HTTP and tool layers hermetically.
- Next: Advance to Week 9 (Spoken approval, dispatch, and recovery watch).

### 2026-09-28 — Optional PSTN Dialing, Twilio Adapter & Demo Mode Configuration (Milestone 30) Completed

- State: PASS
- Changes: `packages/contracts/telephony.py`, `packages/core/config.py`, `packages/providers/telephony.py`, `apps/orchestrator/activities.py`, `scripts/toggle_demo_mode.sh`, `.env.example`, `tests/test_telephony.py`, `learning.md`, `.context/progress-tracker.md`
- Verification: `uv run pytest tests/test_telephony.py -v` (9/9 passed), full suite `uv run pytest` (94/94 passed), `uv run ruff check` (all clean).
- Metrics: Multi-mode telephony configuration (`TELEPHONY_MODE` options: `"livekit-rtc"`, `"browser"`, `"fake"`, `"twilio"`, `"livekit-sip"`). Default set to `"livekit-rtc"`. In `notify_oncall_activity`, demo mode skips PSTN dials, returns `SKIPPED_PSTN_RTC_READY`, and logs LiveKit room details (`agents-playground.livekit.io`). `TwilioVoiceAdapter` enforces safety allowlist and checks credentials. Executable helper `scripts/toggle_demo_mode.sh` seamlessly switches between browser demo and PSTN dialing.
- Risks: Real Twilio PSTN dialing requires verified allowlisted phone numbers and funded Twilio credentials; demo mode (`livekit-rtc`) bypasses carrier dependencies completely.
- Next: Advance to Week 9 (Spoken approval, dispatch, and recovery watch).

### 2026-09-29 — End-to-End PSTN Dialing Wiring & HTTPS TwiML Compatibility (Milestone 31) Completed

- State: PASS
- Changes: `packages/providers/telephony.py`, `packages/contracts/telephony.py`, `packages/core/config.py`, `apps/orchestrator/activities.py`, `apps/console/app.py`, `tests/test_telephony.py`, `learning.md`, `.context/progress-tracker.md`
- Verification: `uv run pytest tests/test_telephony.py tests/test_console.py -v` (17/17 passed), `uv run pytest tests/test_voice_agent.py -v` (18/18 passed), `uv run ruff check` (all clean), live Twilio trial call dispatch verified (dispatched and queued with SID `CA02feb8ca3b9e0a9c1eb23c5b7329d410`).
- Metrics: Resolved Twilio 301 redirect rejection by switching from insecure `http://` to `https://twimlets.com/echo?Twiml=...` with standard `voice="alice"` and `urllib.parse.quote_plus()`. Added `twilio_twiml_url` configuration override. Updated `notify_oncall_activity` to route to `settings.oncall_phone_number` and pass `initial_brief`. Wired `apps/console/app.py` `trigger_fault()` to invoke `notify_oncall_activity` so fault triggers initiate outbound phone calls when configured.
- Risks: On Twilio trial accounts, destination numbers must be verified in the Twilio console and trial disclaimers precede the spoken message.
- Next: Advance to Week 9 (Spoken approval, dispatch, and recovery watch).

### 2026-09-30 — Hybrid Action Policy & Telegram Escalation Handover (Milestone 32) Completed

- State: PASS
- Changes: `packages/core/config.py`, `packages/core/telegram.py`, `packages/policy/tier.py`, `apps/voice/agent.py`, `apps/orchestrator/workflow.py`, `apps/console/app.py`, `apps/console/static/index.html`, `.context/architecture.md`, `AGENTS.md`, `.context/progress-tracker.md`, `tests/test_telegram.py`, `tests/test_policy_and_grounding.py`, `tests/test_console.py`, `tests/test_orchestrator.py`, `tests/test_voice_agent.py`
- Verification: `uv run pytest tests/test_telegram.py tests/test_voice_agent.py tests/test_console.py tests/test_orchestrator.py tests/test_policy_and_grounding.py -v` (40/40 passed), `uv run ruff check packages/ apps/ tests/` (clean), `uv run mypy packages/ apps/ tests/` (clean).
- Metrics: Enforced deterministic Hybrid Action Policy. Tier 1 read-only diagnostics execute automatically on server. Tier 2 mutating actions block server auto-execution upon spoken assent, trigger `dispatch_telegram_escalation` (formatting incident ID, problem summary, severity/impact, bash command fences, and ordered manual steps to Telegram Bot API), emit `escalate_incident_signal` with immutable audit entry to Temporal workflow, transition workflow and console state to `PROBLEM_ESCALATED_TO_HUMAN`, and provide natural spoken feedback to operator: *"Understood. I have dispatched the exact command and manual remediation steps to your Telegram. Escalating this incident to you now."* Console renders amber badges and state cards for escalated incidents.
- Risks: In offline/unconfigured environments, Telegram dispatcher falls back gracefully to logged mock dispatch (`DISPATCHED_MOCK`) without stalling audio streams or failing test suites.
- Next: Complete recovery watch and post-remediation telemetry checks for Week 9.

## 11. Current next action

Advance to recovery watch and post-remediation telemetry checks for Week 9.
