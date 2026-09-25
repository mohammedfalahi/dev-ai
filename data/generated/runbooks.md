# Verified Operational Runbooks

---
runbook_id: RB-PG-001
title: PostgreSQL application connection pool exhaustion
service: checkout-api
severity: SEV-1
owner: Payments Platform
tags: [postgres, connection-pool, checkout, database]
source_url: internal://runbooks/rb-pg-001
last_verified_at: 2026-08-14
---

# PostgreSQL application connection pool exhaustion

## Purpose

Diagnose failures where `checkout-api` cannot acquire a PostgreSQL connection
from its application pool.

## Use this when

Use this runbook when checkout 5xx responses increase and at least one of the
following is true:

- `db_pool_wait_seconds` is above 2 seconds.
- PostgreSQL connections for `checkout-api` exceed 85% of the configured limit.
- Logs contain `asyncpg.exceptions.TimeoutError` or `pool acquire timeout`.

Do not use it as the primary runbook when the PostgreSQL primary health check is
failing or when all applications lose connectivity simultaneously.

## Initial checks — read-only

```bash
kubectl -n production get pods -l app=checkout-api
kubectl -n production logs deploy/checkout-api --since=15m | grep -E 'pool|connection|asyncpg|timeout'
```

```sql
SELECT application_name, state, wait_event_type, count(*) AS connection_count
FROM pg_stat_activity
GROUP BY application_name, state, wait_event_type
ORDER BY connection_count DESC;
```

## Decision points

If many sessions are idle and owned by `checkout-api`, investigate a connection
leak or a pool-size change in the latest deployment. If sessions are active and
waiting on locks, investigate database contention instead. If database activity
is normal, check application CPU, DNS, network reachability, and credentials.

A deployment immediately preceding the first pool-wait increase is a leading
hypothesis, not proof of causation.

## Safe mitigation

A rollout restart of `checkout-api` can release leaked application connections,
but it requires incident approval. Before proposing it, confirm that the
PostgreSQL primary is healthy and that the order queue is not already behind.

Do not increase `max_connections` during an incident without reviewing memory
impact with Database Platform. Do not terminate sessions as an automated action.

## Recovery validation

Confirm checkout 5xx is below 1%, pool wait is below 100 ms, database connection
utilization is below 80%, and a synthetic checkout succeeds. Record the deploy
version, maximum connection count, representative log line, and approval ID.

## Escalation

Escalate to Mateo Silva if lock waits persist for five minutes, utilization stays
above 90%, or the issue recurs after an approved application restart.


---
runbook_id: RB-PG-002
title: PostgreSQL primary availability and replication health
service: postgres-primary
severity: SEV-1
owner: Database Platform
tags: [postgres, primary, replication, database]
source_url: internal://runbooks/rb-pg-002
last_verified_at: 2026-08-21
---

# PostgreSQL primary availability and replication health

## Purpose

Distinguish a PostgreSQL primary outage from application-level connection pool
problems and identify whether replica lag is contributing to stale catalog data.

## Initial checks — read-only

```bash
kubectl -n production get pods -l app=postgres
kubectl -n production describe service postgres-primary
```

```sql
SELECT now(), pg_is_in_recovery(), current_database();
SELECT client_addr, state, sync_state, write_lag, flush_lag, replay_lag
FROM pg_stat_replication;
```

## Decision points

If the primary health check fails and multiple services report connection
refused or DNS errors, classify primary availability as the leading hypothesis.
If the primary is healthy but `replay_lag` is above 30 seconds, investigate the
replica path and catalog freshness separately.

A single application reporting a pool timeout is not sufficient evidence of a
primary outage.

## Safety boundary

Do not promote a replica, modify replication settings, or terminate database
sessions automatically. Those actions require Database Platform approval and a
recorded incident command decision.

## Recovery validation

Confirm primary health checks pass twice, new write transactions succeed, replica
lag returns below ten seconds, and both `checkout-api` and `catalog-api` recover.
Record the observed database role and all relevant timestamps.


---
runbook_id: RB-REDIS-001
title: Redis memory pressure, eviction, and queue impact
service: redis-cache
severity: SEV-1
owner: Platform
tags: [redis, memory, eviction, queue]
source_url: internal://runbooks/rb-redis-001
last_verified_at: 2026-08-18
---

# Redis memory pressure, eviction, and queue impact

## Purpose

Investigate Redis memory pressure and determine whether evictions affect cache
behavior, order queues, or notification delivery.

## Initial checks — read-only

```bash
redis-cli INFO memory
redis-cli INFO stats
redis-cli SLOWLOG GET 20
```

Check the Grafana panels for `redis_memory_used_bytes`, `redis_evicted_keys_total`,
cache hit ratio, and queue depth. A memory level above 90% is an investigation
threshold; it is not by itself proof of customer impact.

## Decision points

If evictions are increasing and the evicted keys belong to cache namespaces,
expect cache misses and higher PostgreSQL reads. If queue depth is increasing or
queue keys are being evicted, treat order processing as at risk. A large-key
scan or a sudden increase in payload size can explain latency without causing
many evictions.

## Safety boundary

Do not run `FLUSHALL`, `FLUSHDB`, or mass key deletion. Do not change eviction
policy during an incident without Platform approval. Cache warming and queue
replay must be coordinated with the owning service.

## Recovery validation

Confirm memory is below 80%, evictions have stopped, queue depth is decreasing,
cache hit ratio is recovering, and no order jobs were lost. Record the largest
key observation if available and preserve the Redis metrics window.


---
runbook_id: RB-STRIPE-001
title: Stripe webhook backlog and signature validation failures
service: worker-orders
severity: SEV-1
owner: Payments Platform
tags: [stripe, webhook, payments, worker]
source_url: internal://runbooks/rb-stripe-001
last_verified_at: 2026-08-25
---

# Stripe webhook backlog and signature validation failures

## Purpose

Determine whether delayed payment state changes are caused by worker failure,
queue backlog, or Stripe signature validation errors.

## Initial checks — read-only

```bash
kubectl -n production get pods -l app=worker-orders
kubectl -n production logs deploy/worker-orders --since=30m | grep -E 'webhook|signature|retry|Stripe'
```

Check oldest webhook age, delivery attempt count, HTTP response code, and worker
queue depth. A backlog older than ten minutes requires Payments Primary review.

## Decision points

Repeated HTTP 5xx responses with healthy signature validation indicate worker or
database failure. Repeated 400 responses containing `signature verification`
indicate a signing-secret or clock configuration problem. Successful delivery
with delayed processing points to queue contention.

Do not confuse Stripe's delivery timestamp with the time the order state was
committed locally.

## Safety boundary

Do not disable signature verification. Do not replay the complete webhook queue
without checking idempotency keys and approval from Payments Platform.

## Recovery validation

Confirm oldest event age is below two minutes, retries are no longer increasing,
order state transitions are idempotent, and a test event reaches the expected
terminal state.


---
runbook_id: RB-K8S-001
title: Kubernetes checkout-api crash loop and rollout regression
service: checkout-api
severity: SEV-1
owner: Payments Platform
tags: [kubernetes, crashloop, deployment, checkout]
source_url: internal://runbooks/rb-k8s-001
last_verified_at: 2026-08-11
---

# Kubernetes checkout-api crash loop and rollout regression

## Purpose

Diagnose a checkout deployment whose pods fail readiness, restart repeatedly, or
serve elevated latency after a rollout.

## Initial checks — read-only

```bash
kubectl -n production get pods -l app=checkout-api -o wide
kubectl -n production describe pod <pod-name>
kubectl -n production rollout status deployment/checkout-api
kubectl -n production rollout history deployment/checkout-api
```

Compare the failing pod version with the last known healthy version. Inspect
termination reason, readiness probe output, image pull status, and configuration
references.

## Decision points

`CrashLoopBackOff` with a missing environment variable suggests configuration or
secret wiring. Readiness failures with healthy containers suggest dependency
reachability or an incompatible probe. A latency increase without restarts may be
a code-path regression rather than a Kubernetes failure.

## Safety boundary

A rollback requires approval from Payments Primary. Do not delete pods one by
one as a substitute for understanding the rollout; that can hide the failure and
make the evidence window harder to reconstruct.

## Recovery validation

Confirm the intended version is serving, readiness remains healthy for ten
minutes, checkout p95 is below 500 ms, and error rate is below 1%.


---
runbook_id: RB-EDGE-001
title: Edge proxy upstream 502 errors
service: edge-proxy
severity: SEV-1
owner: Platform
tags: [edge, nginx, 502, upstream, kubernetes]
source_url: internal://runbooks/rb-edge-001
last_verified_at: 2026-08-09
---

# Edge proxy upstream 502 errors

## Purpose

Diagnose upstream 502 responses at the edge and distinguish an edge routing
problem from unhealthy application pods.

## Initial checks — read-only

```bash
kubectl -n production get endpoints checkout-api
kubectl -n production logs deploy/edge-proxy --since=15m | grep 'upstream'
curl -sS -o /dev/null -w '%{http_code} %{time_total}\n' https://checkout.example.test/healthz
```

Compare the edge 502 rate with direct service health, endpoint count, and
checkout-api readiness. A 502 with zero endpoints points toward service discovery
or pod readiness. A 502 with healthy endpoints requires checking proxy timeout,
TLS, and upstream connection errors.

## Safety boundary

Do not edit proxy routing or bypass TLS verification during an incident. Any
configuration change requires Platform approval and a rollback plan.

## Recovery validation

Confirm endpoint count is stable, edge 502 rate is below 0.5%, direct health and
external health both pass, and no new upstream timeout errors appear for ten
minutes.
