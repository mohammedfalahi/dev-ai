# On-call Voice — Library and Documentation Registry

> Status: Approved technology registry and anti-hallucination guide  
> Last updated: 2026-09-23

## 1. Purpose

This file tells an autonomous coding agent which libraries and primary documentation are acceptable, how to verify APIs, and where provider-specific code may live.

It is not a claim that every listed package is installed or that an API remembered by the model is current. The lockfile and version-appropriate primary docs are authoritative.

## 2. Mandatory API-verification protocol

Before writing code against a dependency:

1. Read the locked package version from `uv.lock`, `pyproject.toml`, frontend lockfile, or image manifest.
2. Open the official documentation for that version, or inspect the installed package's types/source when network access is unavailable.
3. Confirm import path, constructor, async behavior, timeout controls, callback/event shape, and error types.
4. Find or create the repository-owned port that isolates the SDK.
5. Write a minimal contract test using a fake or recorded fixture.
6. Add the verified version, documentation URL, and date to the table below.
7. If the API cannot be verified, stop with `BLOCKED`; do not invent a call signature.

Do not use a blog post, tutorial, generated snippet, or model memory when primary docs or installed types are available.

## 3. Version and dependency policy

- Pin exact production dependency versions in the lockfile.
- Pin container base images by digest for releases.
- Use compatible ranges only in human-edited manifests when the lockfile fixes the actual version.
- Dependabot/Renovate updates must run contract, integration, replay, retrieval, grounding, and latency gates relevant to the package.
- Major upgrades require an ADR when they change contracts, runtime behavior, persistence, telephony, policy, or evaluation.
- Record provider API versions and model identifiers in runtime metadata.
- Never silently switch a model, embedding dimension, voice, or reranker.
- Preserve previous prompt/model/eval versions long enough to reproduce incident output under retention policy.

## 4. Approved primary stack

The `Verified version` column remains `TBD` until implementation pins and checks it.

| Capability | Primary choice | Verified version | Primary docs | Adapter/boundary | First used |
| --- | --- | --- | --- | --- | ---: |
| Runtime | Python 3.12+ | TBD | https://docs.python.org/3.12/ | Repository-wide | W0 |
| Package manager | uv | TBD | https://docs.astral.sh/uv/ | Build tooling | W0 |
| API gateway | FastAPI | TBD | https://fastapi.tiangolo.com/ | `apps/gateway` | W0–W1 |
| Contracts | Pydantic v2 | TBD | https://docs.pydantic.dev/latest/ | `packages/contracts` | W0 |
| Database | PostgreSQL | TBD | https://www.postgresql.org/docs/ | Persistence port | W0 |
| Vector extension | pgvector | TBD | https://github.com/pgvector/pgvector | Knowledge repository | W0–W3 |
| Migrations | Alembic | TBD | https://alembic.sqlalchemy.org/ | Persistence tooling | W0 |
| ORM/query layer | SQLAlchemy 2.x | TBD | https://docs.sqlalchemy.org/en/20/ | Persistence adapters | W0 |
| Durable workflows | Temporal Python SDK | TBD | https://docs.temporal.io/develop/python | `apps/orchestrator` | W0, W5 |
| Cache/bus | Redis Streams **or** NATS JetStream | TBD | https://redis.io/docs/latest/develop/data-types/streams/ / https://docs.nats.io/nats-concepts/jetstream | Event/cache port | W0 |
| Investigator framework | Pydantic AI **or** OpenAI Agents SDK | TBD | https://ai.pydantic.dev/ / https://openai.github.io/openai-agents-python/ | Investigator runner port | W2 |
| Tool protocol | MCP | TBD | https://modelcontextprotocol.io/ | Tool adapter boundary | W2 |
| Voice runtime | LiveKit Agents | TBD | https://docs.livekit.io/agents/ | `apps/voice` | W6 |
| Telephony | LiveKit SIP | TBD | https://docs.livekit.io/telephony/ | Telephony port | W7 |
| Outbound call setup | LiveKit outbound trunk | TBD | https://docs.livekit.io/telephony/making-calls/outbound-trunk | Telephony adapter | W7 |
| SIP carrier | Twilio Elastic SIP Trunking | TBD | https://www.twilio.com/docs/sip-trunking | Carrier adapter/config | W7 |
| Streaming STT | Deepgram | TBD | https://developers.deepgram.com/docs/ | STT port | W6 |
| Voice activity | Silero VAD | TBD | https://github.com/snakers4/silero-vad | Turn detector composition | W6 |
| Semantic endpointing | LiveKit turn detector plugin | TBD | LiveKit Agents docs for pinned version | Turn detector port | W6 |
| Streaming TTS | Cartesia Sonic | TBD | https://docs.cartesia.ai/ | TTS port | W6 |
| Alternative TTS | Deepgram Aura-2 | TBD | https://developers.deepgram.com/docs/tts | TTS port | W6 |
| Policy | Open Policy Agent/Rego | TBD | https://www.openpolicyagent.org/docs/latest/ | `packages/policy` | W4 |
| Observability | OpenTelemetry | TBD | https://opentelemetry.io/docs/languages/python/ | `packages/observability` | W0 |
| Agent tracing | Langfuse | TBD | https://langfuse.com/docs | Trace exporter | W11 |
| Metrics/alerting | Prometheus + Alertmanager | TBD | https://prometheus.io/docs/ / https://prometheus.io/docs/alerting/latest/alertmanager/ | Signal adapters/lab | W0–W1 |
| Error source | Sentry | TBD | https://docs.sentry.io/ | Signal/tool adapter | W1–W2 |
| Network faults | Toxiproxy | TBD | https://github.com/Shopify/toxiproxy | Broken-shop lab | W0 |
| Load generation | k6 | TBD | https://grafana.com/docs/k6/latest/ | Broken-shop/eval | W0 |
| Containers | Docker/Compose | TBD | https://docs.docker.com/ | Local/runtime packaging | W0 |
| Infrastructure as code | Terraform | TBD | https://developer.hashicorp.com/terraform/docs | `infra/`, post-contract stabilization | W10+ |
| CI | GitHub Actions | N/A | https://docs.github.com/actions | `.github/workflows` | W0 |

## 5. Primary conceptual reading

These references from the project specification are the starting set. Verify publication date and API applicability before implementing code.

### Voice and telephony

- LiveKit Agents: https://docs.livekit.io/agents/
- LiveKit Telephony/SIP: https://docs.livekit.io/telephony/
- LiveKit outbound trunk setup: https://docs.livekit.io/telephony/making-calls/outbound-trunk
- Pipecat source and pipeline model: https://github.com/pipecat-ai/pipecat
- OpenAI Realtime API guide: https://developers.openai.com/api/docs/guides/realtime

### Durable orchestration

- Temporal durable multi-agent systems: https://temporal.io/blog/durable-flexible-multi-agent-systems
- Temporal Python developer guide: https://docs.temporal.io/develop/python
- Restate AI agents alternative: https://docs.restate.dev/ai

### Monitoring and incident response

- Prometheus Alertmanager guide: https://betterstack.com/community/guides/monitoring/prometheus-alertmanager/
- AI SRE overview: https://incident.io/blog/what-is-ai-sre-complete-guide-2026
- Incident-management agent patterns: https://www.augmentcode.com/guides/ai-agents-incident-management

### Voice evaluation and provider comparison

- Voice-agent evaluation guide: https://www.coval.ai/blog/voice-ai-agent-evaluation-guide/
- Hamming evaluation framework: https://hamming.ai/resources/how-to-evaluate-voice-agents-2026
- Low-latency TTS overview: https://gradium.ai/content/best-low-latency-tts-apis-2026
- STT provider benchmark overview: https://www.coval.ai/blog/best-speech-to-text-providers-in-2026-independent-benchmarks-and-how-to-choose/

Secondary comparisons may shape an experiment, but official docs and repository measurements decide implementation.

## 6. Provider selection rules

### Investigator framework

Default candidates: Pydantic AI or OpenAI Agents SDK.

Choose after a small Week 2 spike using:

- Strict typed tool and structured-output support.
- Cancellation and timeout behavior.
- Traceability.
- Model/provider portability.
- Ease of deterministic fakes.
- Low framework intrusion into domain code.

LangGraph is acceptable only when explicit graph complexity demonstrably exceeds the simple investigator pipeline. Record the choice in ADR-012.

### Bus/cache

Choose Redis Streams when operational simplicity and existing Redis usage dominate. Choose NATS JetStream when durable fan-out, consumer semantics, and independent messaging operations justify it. Neither is the system of record. Record ADR-011.

### STT

Primary: Deepgram streaming.

Required spike measurements:

- Partial/final latency over telephony audio.
- Word error rate on technical identifiers and drowsy/accented speech.
- Endpointing interaction.
- Reconnection and backpressure behavior.
- Confidence metadata suitable for approval gating.

Alternatives: ElevenLabs Scribe v2 Realtime, AssemblyAI Universal-Streaming, or a compatible realtime Whisper service. Changing provider must not change the internal transcript contract.

### TTS

Primary candidates: Cartesia Sonic and Deepgram Aura-2.

Measure:

- Time to first byte.
- Streaming/cancellation behavior.
- Phone-band intelligibility.
- Pronunciation of service names, numbers, and commands.
- WebSocket recovery.
- Cost.

ElevenLabs Flash v2.5 is an optional quality experiment. Record the choice in ADR-013.

### Conversation model

Use a fast text model with streaming and structured tool support. The model is selected by measured grounding, first-token latency, tool reliability, and cost on the versioned voice eval set. Do not put a model identifier in domain code.

Speech-to-speech stays experimental until it can satisfy the same pre-audio claim and command validation contract.

### Embeddings

Candidates from the specification:

- `gemini-embedding-001`
- Voyage-3
- `bge-m3` self-hosted

Store model identifier and dimension with every embedding. A model change requires a new embedding namespace and full reindex; never mix vectors from different models/dimensions.

### Reranker

Candidates:

- Cohere Rerank 3.5
- Voyage rerank
- `bge-reranker-v2-m3`

Select by retrieval eval improvement, latency, data handling, and cost. The reranker cannot bypass eligibility filters.

### Policy engine

OPA/Rego is primary for command tiering and allowlists. Cedar is an alternative if fine-grained principal/action/resource authorization becomes the dominant use case. Policy output must match the typed internal decision contract.

### Telephony

Primary: LiveKit SIP with Twilio Elastic SIP Trunking.

Alternatives: Telnyx, Plivo, or LiveKit native phone numbers. All implementations must support or emulate:

- Outbound dialing.
- Signed callbacks.
- AMD/voicemail result.
- Stable provider call ID.
- Termination/cancellation.
- Spend and destination controls.

## 7. Internal adapter contracts

Provider SDKs implement repository-owned protocols. Exact signatures are finalized in code, but responsibilities are fixed.

### Telemetry readers

```python
class LogReader(Protocol):
    async def search(self, query: LogQuery, *, timeout: float) -> LogResult: ...

class MetricsReader(Protocol):
    async def query(self, query: MetricQuery, *, timeout: float) -> MetricResult: ...

class TraceReader(Protocol):
    async def search(self, query: TraceQuery, *, timeout: float) -> TraceResult: ...
```

All results contain source IDs, observation/collection times, bounded redacted data, and typed errors.

### Knowledge providers

```python
class Embedder(Protocol):
    async def embed(self, texts: Sequence[str]) -> EmbeddingBatch: ...

class Reranker(Protocol):
    async def rerank(self, query: str, candidates: Sequence[ChunkCandidate]) -> RankedChunks: ...
```

### Speech providers

```python
class StreamingSTT(Protocol):
    async def transcribe(self, audio: AsyncIterator[AudioFrame]) -> AsyncIterator[TranscriptEvent]: ...

class StreamingTTS(Protocol):
    async def synthesize(self, text: AsyncIterator[ValidatedSpeechUnit]) -> AsyncIterator[AudioFrame]: ...
```

### Telephony provider

```python
class TelephonyProvider(Protocol):
    async def dial(self, request: DialRequest, *, idempotency_key: str) -> DialResult: ...
    async def hang_up(self, call_id: str) -> None: ...
```

### Dispatch provider

```python
class ActionDispatcher(Protocol):
    async def dispatch(self, approved: ApprovedSnippet, *, idempotency_key: str) -> DispatchResult: ...
```

There is intentionally no production `MutationExecutor` in the MVP.

## 8. Documentation capture record

When a dependency is first integrated or upgraded, append a row:

| Date | Package/provider | Version/API | Docs verified | Contract test | Notes |
| --- | --- | --- | --- | --- | --- |
| — | — | — | — | — | No integrations verified yet |

Recommended note format:

```text
- Verified import and async method signatures against <URL or installed path>.
- Confirmed timeout/cancellation semantics: <summary>.
- Confirmed callback/error types: <summary>.
- Adapter: <module>.
- Contract test: <test name>.
- Known limitation: <limitation>.
```

## 9. Documentation freshness and offline behavior

- Prefer versioned official docs over “latest” pages when both exist.
- Record the verification date and exact version.
- If external docs are unavailable, inspect installed source, type stubs, CLI help, and package examples included with that version.
- Do not install a different version merely because its docs are accessible.
- Do not scrape credentials, account data, or provider dashboards into the repository.
- If a required behavior cannot be verified offline, create a blocked task with the smallest live-doc question.

## 10. Security and legal review triggers

Require human review before adopting/upgrading a library or service that:

- Receives logs, prompts, runbooks, transcripts, recordings, phone numbers, or production metadata.
- Executes infrastructure tools or stores credentials.
- Changes data residency, retention, training, or subprocessors.
- Introduces AGPL/SSPL or other licensing obligations not already approved.
- Adds native code or privileged container access.
- Changes telephony recording, caller ID, emergency calling, or country coverage.
- Sends evaluation data to a third party.

Record terms/data-handling review outside this file and link it from an ADR.

## 11. Alternative-stack boundaries

Credible alternatives remain acceptable when the internal contract and gates are preserved:

- Voice pipeline control: Pipecat.
- Managed voice layer: Vapi or Retell for an MVP.
- Telephony: Telnyx or Plivo.
- Durable workflows: Restate or Inngest after an ADR.
- Vector store: Qdrant after measured Postgres limits.
- Policy: Cedar.
- Agent observability: Braintrust.
- Voice eval platform: Coval or Hamming.
- Hosting: Fly.io or Railway; Kubernetes only with existing operational maturity.

A switch is not a rewrite excuse. Migrate through ports and contract tests.

## 12. Library adoption checklist

- [ ] Exact version is pinned.
- [ ] Primary docs or installed source were verified.
- [ ] License and data handling are acceptable.
- [ ] SDK is behind an internal adapter.
- [ ] Timeout, retry, cancellation, and idempotency are explicit.
- [ ] Errors are translated into the internal taxonomy.
- [ ] Contract tests cover success, malformed data, timeout, and provider failure.
- [ ] Telemetry is instrumented and redacted.
- [ ] Cost/spend controls exist for paid calls.
- [ ] Upgrade and rollback path is documented.
- [ ] The documentation capture record is updated.