# On-call Voice

> **A deterministic safety aid for human operators.**  
> Detects production failures, groups noisy alerts, investigates root causes in under 60 seconds, calls the on-call engineer, explains the best-supported hypothesis in plain speech, and enforces strict, exact spoken assent before dispatching mutating remediations.

[![CI/CD Quality Gate](https://img.shields.io/badge/CI%2FCD-Passing-brightgreen?style=flat-square)](#)
[![Python Version](https://img.shields.io/badge/Python-%3E%3D3.12-blue?style=flat-square)](#)
[![Code Style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](#)
[![Type Checker: mypy strict](https://img.shields.io/badge/types-mypy_strict-blue.svg)](#)
[![Deterministic Evals](https://img.shields.io/badge/Eval%20Matrix-100%25%20Pass-brightgreen.svg)](#)
[![Safety Model](https://img.shields.io/badge/Safety-Default%20Deny-red.svg)](#)

---

## 🏛️ Architecture & System Planes

The system is built on a **"Two Brains on Two Clocks"** architectural model:
1. **The Slow Brain (Investigator)** runs *before* the phone rings. It operates with a 30–60 second wall-clock budget using a frontier reasoning model through typed tools. It collects bounded logs, metrics, traces, deploys, and runbooks to produce a compact, validated **Incident Context Object (ICO)**.
2. **The Fast Brain (Voice Agent)** runs *during* the call. It operates with a sub-second perceived conversational turn budget ($p50 \le 800\text{ ms}$, $p95 < 1\text{ s}$). It streams bidirectional speech via LiveKit Agents and Gemini Live Native Audio directly from the precomputed ICO, enforcing deterministic grounding and action policies without executing heavy database queries on the hot path.

### End-to-End System Data Flow

```text
[ Monitoring & Probes ] (Prometheus / Sentry / Alerts)
         │
         │ Signed HMAC-SHA256 Webhooks + Timestamp Tolerances
         ▼
┌────────────────────────────────────────────────────────────────────────┐
│ INGEST & TRIAGE GATEWAY (apps/gateway)                                  │
│  ├─ Verify HMAC-SHA256 signature and timestamp tolerance (±300s)       │
│  ├─ Normalize payload into NormalizedAlert contract                    │
│  ├─ Compute stable SHA-256 fingerprint (strips volatile timestamps)   │
│  ├─ 60s Sliding-Window Deduplication (50 alerts -> 1 incident)         │
│  └─ Evaluate deterministic severity policy (voice_page / message / sup)│
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   │ Upsert Incident & Start Workflow
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ DURABLE ORCHESTRATOR (apps/orchestrator - Temporal)                    │
│  Workflow: incident/<incident_id>                                      │
│  ├─ State: NEW -> TRIAGED -> INVESTIGATING -> BRIEF_READY -> DIALING   │
│  ├─ Enforces hard 60s investigation timeout & partial brief fallback   │
│  └─ Durable 90s escalation timer for human-in-the-loop acknowledgment  │
└───────┬────────────────────────────────────────────────────────┬───────┘
        │                                                        │
        │ Step 1: Execute Investigation                          │ Step 2: Handoff ICO
        ▼                                                        ▼
┌──────────────────────────────────────────┐   ┌──────────────────────────────────────────┐
│ INVESTIGATOR - SLOW BRAIN                │   │ VOICE AGENT - FAST BRAIN                 │
│ (apps/investigator)                      │   │ (apps/voice - LiveKit + Gemini Live)     │
│  ├─ Fan-out read-only evidence collection│   │  ├─ Deliver empathetic precomputed brief │
│  │   (Logs, metrics, traces, deploys)    │   │     ("Hello, sorry to wake you up...")   │
│  ├─ Query Knowledge Vault (PostgreSQL)   │   │  ├─ Native duplex audio stream (<800ms)  │
│  │   ├─ Dense: pgvector (768d vectors)   │   │  ├─ Grounded follow-up Q&A from ICO      │
│  │   ├─ Sparse: tsvector (FTS BM25)      │   │  ├─ Deterministic Tool Calling           │
│  │   ├─ Reciprocal Rank Fusion (k=60)    │   │  │   (execute_remediation_command)       │
│  │   └─ MS-MARCO Cross-Encoder Rerank    │   │  ├─ Substring runbook AST validation     │
│  │       (Refusal Gate: logit < -8.5)    │   │  ├─ Policy classification (Tier 1 vs 2)  │
│  ├─ Formulate grounded hypothesis        │   │  └─ Spoken assent handshake (confirm/go) │
│  └─ Emit validated IncidentContextObject │   └────────────────────┬─────────────────────┘
└──────────────────────────────────────────┘                        │
                                                                    │ Temporal Signal / SMS / Slack
                                                                    ▼
                                               ┌──────────────────────────────────────────┐
                                               │ ACTION & DISPATCH GATEWAY                │
                                               │  ├─ Verify exact spoken confirmation     │
                                               │  ├─ Generate signed SHA-256 audit record │
                                               │  ├─ Forward approved snippet to operator │
                                               │  └─ ZERO autonomous mutation in MVP      │
                                               └──────────────────────────────────────────┘
```

### System Planes & Responsibilities

| System Plane | Owns | Must Not Own | Failure Modes Prevented |
| --- | --- | --- | --- |
| **Signal** | Detection, alert emission, telemetry probes. | Incident grouping, voice logic. | Missing upstream production outages. |
| **Ingest & Triage** | HMAC verification, timestamp checks, fingerprinting, sliding-window dedupe, severity scoring. | Unbounded investigation, conversational logic. | Alert storms overloading the orchestrator (50 related alerts collapse into exactly 1 incident); webhook replay attacks. |
| **Orchestrator** | Durable incident lifecycle (Temporal), timers, retries, worker failover, escalation ladders. | Non-deterministic side effects or direct network I/O in workflow code. | Lost escalation states, worker crash state corruption, duplicate phone calls. |
| **Investigator** | Parallel evidence acquisition, structure-aware Hybrid RAG, hypothesis formulation, ICO generation. | Outbound calling, policy enforcement, command mutation. | Diagnostic hallucinations, context window overflow, unbounded investigation delays (>60s). |
| **Voice Agent** | Low-latency duplex speech streaming, conversational turn management, empathetic brief delivery. | Heavy database queries, RAG lookups, policy classification. | High-latency turn delays (>1s), TTS mispronunciation of raw Markdown/syntax, hallucinated operational procedures. |
| **Action & Policy** | Command tiering, AST-verbatim runbook validation, deterministic spoken assent FSM, signed audit logs. | Model-based authorization judgment. | Unauthorized infrastructure mutations, prompt-injection attacks, accidental confirmation from conversational filler. |
| **Memory** | Relational datastore, append-only digest-chained audit trails, evaluation datasets, postmortems. | Silently promoting unverified model outputs into operational runbooks. | Audit tampering, database state divergence, split-brain vector indexing. |

### Grounding Contract & Safety Rules

Every statement emitted by the system is strictly bound to one of three categories:

| Claim Class | Required Source | Spoken & System Behavior |
| --- | --- | --- |
| **Observed** | Raw telemetry, metrics, logs, or immutable incident facts with source ID and timestamp. | Stated as an empirical observation, including timestamp and magnitude (e.g., *"Error rate increased to 94% at 02:58 UTC"*). |
| **Retrieved** | Eligible runbook chunks with chunk ID, owner, and verification freshness date. | Explicitly names the procedure and surfaces its verification freshness. |
| **Inferred** | Model reasoning grounded exclusively in cited observations or retrieved runbook chunks. | Verbally qualified as a hypothesis or best-supported explanation (e.g., *"Our leading hypothesis is connection pool exhaustion..."*). |

#### The Refusal Protocol
When an alert represents an undocumented or out-of-domain failure, the hybrid retriever's Cross-Encoder produces negative logits below the calibrated refusal gate (`min_rerank_score = -8.5`). The system enters the `UNDOCUMENTED_INCIDENT` state:
1. Candidate runbooks are set to empty (`[]`).
2. Proposed actions are cleared (`None`).
3. The Voice Agent refuses procedural instructions using deterministic phrasing: *"I don't have information on that. No verified runbook applies to this failure."*
4. Hallucinated remediation advice is structurally prevented.

#### Human-in-the-Loop Protocol
* **Tier 1 (Read-Only Diagnostics)**: Read-only operations (`kubectl get pods`, `SELECT ...`, `curl -I`). Allowed to execute automatically or via standard request because they produce no mutating side effects.
* **Tier 2 (Mutating Remediations)**: State-altering operations (`kubectl rollout restart`, `ALTER SYSTEM`, `redis-cli FLUSHDB`, scaling pods).
  * **Default Deny**: Evaluated via deterministic regex/OPA rules, never model judgment.
  * **Verbatim AST Match**: The candidate command must exist *word-for-word* within a markdown code fence (` ```bash ` or ` ```sql `) of an eligible, verified runbook chunk.
  * **Spoken Assent Handshake**: Requires explicit conversational verbal assent (*"confirm"*, *"go ahead"*, *"yes please"*, *"proceed"*, *"do it"*). Negative modifiers (*"no"*, *"don't"*, *"wait"*, *"cancel"*) fail closed immediately.
  * **Human Execution Default**: In the MVP, approved commands are dispatched to authorized text channels (Slack/SMS) for the engineer to review and paste. The system executes zero autonomous Tier 2 mutations.

---

## ✨ Core Features & Technical Stack

* **Low-Latency Duplex Voice**: Powered by LiveKit Agents and the Gemini Live Multimodal Realtime API (`gemini-3.8-live` with automated failover to `gemini-live-2.5-flash-native-audio` on Vertex AI). Achieves native audio streaming with Time-to-First-Audio under 450ms and conversational turns under 800ms.
* **Structure-Aware Hybrid RAG**:
  * Chunker parses markdown into structural H2/H3 procedure units, protecting atomic code fences and enriching `search_text` with hierarchical breadcrumbs.
  * Dual-representation PostgreSQL 16 schema combining dense `vector(768)` embeddings (via `gemini-embedding-001` with Matryoshka Representation Learning) and sparse `tsvector` full-text search.
  * Reciprocal Rank Fusion ($k=60$) balances lexical precision (exact error codes) and semantic recall (synonyms).
  * Local MS-MARCO Cross-Encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`) reranks Top-5 candidates with sub-15ms latency and an empirical refusal gate.
* **Durable Orchestration (Temporal)**: Incident lifecycles are modeled as deterministic workflows (`IncidentLifecycleWorkflow`) with event sourcing, idempotent activities, 60s investigation deadlines, and 90s escalation timeouts.
* **Deterministic Policy Gates**: Eliminates LLM prompt-judgment by enforcing strict Python regex command classification (`classify_command`) and verbatim code-fence substring matching (`validate_action`).
* **Multi-Mode Telephony Adapter**:
  * `livekit-rtc` (Default): Connect directly via browser WebRTC using the LiveKit Agent Playground.
  * `twilio`: Outbound cellular PSTN dialing with HTTPS TwiML echo compatibility and E.164 normalization.
  * `fake`: In-memory deterministic sink for offline CI test suites.
  * `livekit-sip`: Outbound carrier SIP trunking.
* **Full-Stack AI Observability (Langfuse v4)**: Deep hierarchical trace graphs (`agent`, `retriever`, `generation`, `tool`, `guardrail`), automated token usage tracking, and recursive PII/credential scrubbing with zero-crash offline fallback.
* **2-Page Developer Console**:
  * **Operations & Chaos Dashboard (`/`)**: Inject chaos faults into `labs/broken-shop`, monitor real-time gateway deduplication, inspect LiveKit call status, and execute fault resets.
  * **Triage Forensics & Evaluation Hub (`/triage`)**: Inspect structured ICO cards, view raw JSON contracts, and run the automated 3-Tier Evaluation Matrix on demand.

### Technology Stack

| Domain | Technology / Tool | Version / Specification |
| --- | --- | --- |
| **Language & Runtime** | Python | `>=3.12` |
| **Package Management** | `uv` | Locked workspace via `uv.lock` |
| **API Framework** | FastAPI / Uvicorn | `fastapi>=0.141.1`, `uvicorn>=0.54.0` |
| **Data Contracts** | Pydantic v2 & Pydantic Settings | `pydantic>=2.0`, `pydantic-settings>=2.15.0` |
| **Orchestration** | Temporal IO Python SDK | `temporalio>=1.33.0` |
| **Primary Datastore** | PostgreSQL 16 + `pgvector` | `psycopg[binary]>=3.2.0`, `vector(768)` |
| **Dense Embeddings** | Google GenAI SDK | `gemini-embedding-001` (768-dim MRL) |
| **Lexical Search** | PostgreSQL FTS & Rank-BM25 | `tsvector`, `rank-bm25>=0.2.2` |
| **Reranking** | Sentence-Transformers | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| **LLM Reasoning** | Gemini 2.5 Flash / Gemini 3.5 Flash Lite | Structured output via `response_schema` |
| **Realtime Voice** | LiveKit Agents & Google Realtime Plugin | `livekit-agents>=1.8.3`, `livekit-plugins-google>=1.8.3` |
| **Voice Models** | Gemini Live Native Audio | Primary: `gemini-3.8-live` (Studio); Fallback: `gemini-live-2.5-flash-native-audio` (Vertex) |
| **AI Observability** | Langfuse SDK v4 | `langfuse>=4.15.6`, OpenTelemetry primitives |
| **Code Quality** | Ruff, mypy strict, pytest | `ruff>=0.16.8`, `mypy>=2.3.1`, `pytest>=9.1.1` |

---

## 🗂️ Monorepo Directory Layout

```text
/Users/falahi/DEV_AI/
├── .context/                       # Living architectural specifications and system contracts
│   ├── architecture.md             # Normative system architecture and ADR catalog
│   ├── build-plan.md               # 12-week execution milestone roadmap
│   ├── code-standards.md           # Coding standards, package boundaries, and typing rules
│   ├── library-docs.md             # Verified third-party SDK syntax and integration patterns
│   ├── progress-tracker.md         # Live execution record and milestone verification gates
│   └── project-overview.md         # Mission, product promises, and release scorecards
├── apps/                           # Top-level executable application entrypoints
│   ├── console/                    # 2-Page Developer Console & Evaluation Hub
│   │   ├── app.py                  # FastAPI server for dashboard routes & drill APIs
│   │   └── static/                 # Static web interfaces (index.html, triage.html)
│   ├── gateway/                    # Ingestion plane
│   │   ├── app.py                  # Webhook receiver with HMAC and timestamp verification
│   │   └── dedupe.py               # SHA-256 fingerprinting & 60s sliding window deduplicator
│   ├── investigator/               # Slow-brain analytical worker
│   │   └── engine.py               # Evidence aggregator, RAG caller, and ICO builder
│   ├── orchestrator/               # Workflow orchestration plane
│   │   ├── activities.py           # Idempotent Temporal activities (investigate, notify, escalate)
│   │   └── workflow.py             # IncidentLifecycleWorkflow state machine
│   └── voice/                      # Fast-brain conversational plane
│       └── agent.py                # LiveKit voice worker, Gemini Live agent, and tool dispatcher
├── data/                           # Ingestion data fixtures and knowledge corpora
│   └── generated/
│       └── runbooks.md             # 20 operational runbooks (129 structure-aware chunks)
├── evals/                          # Pure-code, multi-tier automated evaluation framework
│   ├── benchmarks/
│   │   └── run_retrieval_benchmark.py  # Pure rank metrics (Recall@K, MRR, Refusal precision)
│   ├── datasets/
│   │   └── golden_dataset.jsonl    # Golden evaluation cases spanning 6 failure taxonomies
│   ├── generation/
│   │   ├── eval_grounding.py       # Verbatim AST code fence and forbidden claim checkers
│   │   └── run_generation_eval.py  # Generation safety runner & ASCII scorecard
│   ├── run_eval_matrix.py          # Consolidated 3-Tier Evaluation Matrix runner
│   └── schemas.py                  # Pydantic schema for golden benchmark cases
├── infra/                          # Infrastructure provisioning and migrations
│   ├── docker-compose.yml          # PostgreSQL 16 + pgvector container definition
│   ├── run_migrations.py           # Automated schema runner
│   └── migrations/
│       └── 001_init_schema.sql     # Core tables, vector(768) columns, HNSW & GIN indexes
├── labs/                           # Breakable testbeds
│   └── broken_shop/                # FastAPI checkout service with injectable fault profiles
│       └── app.py                  # Fault endpoints (pool exhaustion, OOM, 5xx storm, deadlock)
├── packages/                       # Inward-pointing shared libraries
│   ├── contracts/                  # Pydantic domain models (Alert, Incident, ICO, Telephony)
│   ├── core/                       # Centralized configuration (config.py via pydantic-settings)
│   ├── knowledge/                  # RAG pipeline (chunker.py, ingest.py, hybrid_search.py)
│   ├── observability/              # Langfuse v4 tracing client, span helpers, PII redactor
│   ├── policy/                     # Command tiering (tier.py) and grounding validator
│   └── providers/                  # Outbound adapters (telephony.py: Fake, Twilio, LiveKit SIP)
├── scripts/                        # Utility scripts
│   ├── run_console.py              # Single-command concurrent startup for console & broken shop
│   └── toggle_demo_mode.sh         # Fast CLI switch between browser WebRTC and PSTN Twilio
├── spikes/                         # Mathematical and algorithmic proof-of-concept scripts
│   ├── 01_embeddings.py            # Cosine similarity and dimensionality verification
│   ├── 02_bm25.py                  # BM25Okapi sparse lexical scoring
│   ├── 03_reranker.py              # Cross-Encoder joint self-attention scoring
│   └── 04_rrf.py                   # Reciprocal Rank Fusion rank merging
└── tests/                          # Automated test suites (94+ passing unit/contract tests)
```

---

## 🚀 Onboarding & Development Guide

### Prerequisites
* **Python 3.12+**
* **`uv` Package Manager** (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
* **Docker & Docker Compose** (for PostgreSQL 16 + pgvector)

### 1. Environment Setup

Clone the repository and install locked dependencies:
```bash
git clone https://github.com/falahi/dev-ai.git
cd dev-ai
cp .env.example .env
uv sync
```

Review `.env` settings. Safe defaults are enabled out of the box (`TELEPHONY_MODE="livekit-rtc"`, mutation deny-all, no paid provider required for local test suites). For full voice and AI features, configure:
```dotenv
GEMINI_API_KEY="your-google-ai-studio-key"
# Optional for enterprise Vertex AI failover:
GOOGLE_CLOUD_PROJECT="your-project-id"
GOOGLE_CLOUD_LOCATION="us-central1"

# Optional for live tracing:
LANGFUSE_PUBLIC_KEY="pk-lf-..."
LANGFUSE_SECRET_KEY="sk-lf-..."
LANGFUSE_BASE_URL="https://cloud.langfuse.com"
```

### 2. Infrastructure & Database Initialization

Start the PostgreSQL datastore and execute the database schema migration:
```bash
docker-compose up -d
uv run python infra/run_migrations.py
```

### 3. Knowledge Vault Ingestion

Ingest the 20 operational runbooks into PostgreSQL with MRL 768-dim embeddings and auto-generated `fts` tsvectors:
```bash
uv run python -m packages.knowledge.ingest
```

### 4. Launching the Multi-Agent Developer Console

Start both the Broken Shop simulator (port `8081`) and the Developer Console (port `8000`) concurrently:
```bash
uv run python scripts/run_console.py
```

* **Control Room (`http://localhost:8000/`)**: Trigger simulated incidents (Connection Pool Exhaustion, Redis OOM, 502 Storm), inspect gateway alert deduplication counters, view call states, and test spoken assent resolutions.
* **Triage Hub (`http://localhost:8000/triage`)**: Inspect the structured Incident Context Object and trigger the 3-Tier Evaluation Matrix on demand.

### 5. Running the Voice Agent Worker

To launch the LiveKit Agents worker in offline simulation or live WebRTC mode:
```bash
uv run python -m apps.voice.agent dev
```

---

## 🧪 Testing, Evaluation & Safety Verification

The repository replaces non-deterministic "LLM-as-a-judge" evaluation with a **Multi-Tier Evaluation Matrix** combining pure mathematical rank statistics, deterministic AST code-fence validation, and strict negative claim scans.

### Executing Unit & Contract Tests
Run the entire 94-test hermetic test suite offline:
```bash
uv run pytest -v
```

Run static type checking and linting:
```bash
uv run ruff check .
uv run mypy packages/ apps/ evals/ tests/
```

### The Consolidated 3-Tier Evaluation Matrix
Execute the multi-tier benchmark against the 21-case golden dataset:
```bash
uv run python evals/run_eval_matrix.py --strict --output-json eval-report.json
```

```text
========================================================================================
                      CONSOLIDATED EVALUATION MATRIX SCORECARD
========================================================================================
[TIER 1: RETRIEVAL CANDIDATE GATES]
  Recall@1:                     1.0000 (Target: >= 0.7000) -> [PASS]
  Recall@3:                     1.0000 (Target: >= 0.8500) -> [PASS]
  Recall@5:                     1.0000 (Target: >= 0.9000) -> [PASS]

[TIER 2: RERANKING & REFUSAL GATES]
  Mean Reciprocal Rank (MRR):   1.0000 (Target: >= 0.8000) -> [PASS]
  Refusal Precision:            1.0000 (Target: == 1.0000) -> [PASS]
  Hard Negatives at Rank 1:          0 (Target: == 0)      -> [PASS]

[TIER 3: GENERATION & SAFETY GROUNDING GATES]
  Verbatim AST Command Match:   100.0% (Target: >= 85.0%)  -> [PASS]
  Forbidden Claim Violations:     0.0% (Target: == 0.0%)   -> [PASS]
  Refusal Generation Accuracy:  100.0% (Target: == 100.0%) -> [PASS]
  Overall Grounding Pass Rate:  100.0% (Target: >= 90.0%)  -> [PASS]
========================================================================================
FINAL VERDICT: ALL QUALITY GATES PASSED [PASS]
========================================================================================
```

* **Tier 1 (Retrieval Recall)**: Verifies that hybrid dense and sparse search surfaces ground-truth runbooks into candidate pools.
* **Tier 2 (Reranking & Refusal)**: Verifies that the MS-MARCO Cross-Encoder places the correct runbook at Rank 1 and refuses uncataloged faults.
* **Tier 3 (Safety Grounding)**: Verifies that every proposed remediation command matches a runbook code fence verbatim, that policy tiers are assigned deterministically, and that the agent never falsely claims a system has been restarted or modified.

---

## 🗺️ Completed Milestones & Roadmap

### Completed Milestones

* **Milestone 1–5: Retrieval & Algorithmic Spikes**
  * Validated cosine similarity math, BM25Okapi term frequency/IDF, MS-MARCO Cross-Encoder joint self-attention, MRL 768-dim embeddings, and Reciprocal Rank Fusion ($k=60$).
* **Milestone 6–9: Datastore & Hybrid Retrieval Engine (Week 3)**
  * Initialized PostgreSQL 16 + pgvector datastore with dual-representation `vector(768)` and generated `fts` tsvector columns.
  * Implemented structure-aware markdown chunking and ingested 20 canonical runbooks (129 chunks).
  * Implemented `search_runbooks` with hybrid RRF pooling and calibrated Cross-Encoder refusal gate (`min_rerank_score = -8.5`).
* **Milestone 10–12: Contracts & Investigator Slow Brain (Week 2)**
  * Authored Pydantic v2 domain schemas (`NormalizedAlert`, `IncidentRecord`, `IncidentContextObject`).
  * Built `apps/investigator/engine.py` producing strictly validated ICOs via Gemini 2.5 Flash structured outputs within the 60-second budget.
* **Milestone 13: Grounding Validator & Action Policy (Week 4)**
  * Implemented deterministic regex command classification (`classify_command`) separating Tier 1 Read-Only from Tier 2 Mutating actions.
  * Implemented `GroundingValidator.validate_action` demanding verbatim substring inclusion in eligible runbook content.
* **Milestone 14–16: Developer Console & Simulator (Week 0)**
  * Built `apps/console` and `labs/broken-shop` supporting reproducible fault injection (connection pool exhaustion, OOM, 5xx storms, deadlocks).
* **Milestone 17: Durable Orchestration (Week 5)**
  * Implemented Temporal `IncidentLifecycleWorkflow` with event sourcing, durable 90s escalation timers, acknowledgment signals, and status queries.
* **Milestone 18: Ingestion, Deduplication & Severity (Week 1)**
  * Built FastAPI gateway with HMAC-SHA256 signature verification, ±300s timestamp window, stable SHA-256 fingerprinting, and 60s sliding window deduplication collapsing 50 alerts into 1 incident.
* **Milestone 19–23: Multi-Tier Evaluation Framework & CI Gates**
  * Created 21-case golden evaluation dataset (`golden_dataset.jsonl`) covering 6 failure categories.
  * Built pure-code benchmark runners for Retrieval (Recall/MRR) and Generation (AST Command Matching, Negative Claim Scans).
  * Integrated Langfuse v4 tracing with safe offline fallback and automated PII redaction.
  * Implemented `evals/run_eval_matrix.py` and GitHub Actions CI workflow (`.github/workflows/eval.yml`).
* **Milestone 24–27: Fast-Brain Voice Architecture (Week 6 & Week 8)**
  * Migrated voice pipeline to LiveKit Agents with Gemini Live Native Audio (Speech-to-Speech) for sub-800ms conversational turns.
  * Implemented resilient model factory (`get_realtime_model`): Google AI Studio (`gemini-3.8-live`) with zero-downtime failover to Vertex AI (`gemini-live-2.5-flash-native-audio`).
  * Engineered empathetic conversational briefing (*"Hello, sorry to wake you up..."*) and flexible spoken assent handshake engine (*"go ahead"*, *"confirm"*, *"yes please"*, *"do that"*).
* **Milestone 28–31: Full-Duplex Web Console & PSTN Telephony (Week 7)**
  * Built 2-page Developer Console with real-time incident resolution polling and fault lifecycle resets (`POST /api/faults/reset`).
  * Implemented multi-mode telephony port (`livekit-rtc`, `browser`, `fake`, `twilio`, `livekit-sip`) with strict E.164 normalization, destination allowlists, and global kill switch.
  * Resolved carrier webhook redirect errors by wiring native HTTPS TwiML echo integration (`https://twimlets.com/echo?Twiml=...`).

### Current Status & Roadmap

```text
[PASS] Week 0:  Repository, contracts, and breakable lab
[PASS] Week 1:  Signal ingest, dedupe, and severity policy
[PASS] Week 2:  Investigator and evidence model
[PASS] Week 3:  Knowledge vault and hybrid retrieval
[PASS] Week 4:  Grounding validator and action policy
[PASS] Week 5:  Durable incident orchestration
[PASS] Week 6:  Offline conversational voice loop
[PASS] Week 7:  SIP and controlled telephony
[PASS] Week 8:  Integrate Investigator and Voice
[ACTIVE] Week 9:  Spoken approval, dispatch, and recovery watch
[PENDING] Week 10: Escalation and night-survival hardening
[PENDING] Week 11: Evaluation, compliance, and controlled pilot
```

* **Week 9 (Active)**: Completing the human-gated remediation handoff: signing SHA-256 approval audit records, linking exact transcript audio spans, and dispatching approved command snippets to authorized Slack and SMS channels with objective post-remediation telemetry monitoring.
* **Week 10**: Responder night-survival hardening, chaos testing under worker and datastore partitions, and automated multi-channel escalation ladders.
* **Week 11**: End-to-end compliance review, recording-consent controls, pilot game days, and auto-drafted postmortem generation.

---

## 📄 License & Attribution

Internal engineering artifact and safety aid. Designed for human-in-the-loop incident response. All mutating commands require explicit human assent prior to dispatch.
