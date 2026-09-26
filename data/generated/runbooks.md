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

---
runbook_id: RB-AUTH-001
title: JWT Signing Key Invalidation and JWKS Cache Failure
service: auth-service
severity: SEV-1
owner: Identity Platform
tags: [jwt, jwks, authentication]
source_url: internal://runbooks/rb-auth-001
last_verified_at: 2026-09-20
---

# JWT Signing Key Invalidation and JWKS Cache Failure

## Purpose

Restore authentication when JWT verification fails because signing keys changed, the JWKS endpoint is unavailable, or auth-service instances retain stale JWKS data.

## Use this when

- Valid users receive HTTP 401 responses above 5% for five minutes.
- Logs contain `kid not found in JWKS`, `invalid signature`, or `JWKS cache refresh failed`.
- Failures begin immediately after a signing-key rotation.
- The issuer's JWKS endpoint returns stale keys, errors, or excessive cache headers.

## Initial checks — read-only

```bash
kubectl -n prod get pods -l app=auth-service -o wide
kubectl -n prod logs deployment/auth-service --since=15m | grep -E 'kid not found|invalid signature|JWKS cache'
kubectl -n prod get deployment auth-service -o yaml | grep -E 'JWKS|ISSUER|CACHE'
curl -fsS -D /tmp/jwks.headers https://auth.northstar.example/.well-known/jwks.json | jq '.keys[] | {kid,alg,use}'
cat /tmp/jwks.headers | grep -iE 'cache-control|age|etag'
```

## Decision points

- If the token `kid` is absent from the authoritative JWKS response, stop and escalate to Identity Platform.
- If the key exists remotely but only some pods reject it, treat the incident as a stale per-pod cache.
- If all pods fail to reach the endpoint, investigate DNS, TLS, and network policy before restarting.
- If the issuer or audience is wrong, correct configuration through the deployment pipeline.

## Safe mitigation

With incident commander approval, restart auth-service gradually to clear in-memory JWKS caches:

```bash
kubectl -n prod rollout restart deployment/auth-service
kubectl -n prod rollout status deployment/auth-service --timeout=10m
```

Keep at least 75% of replicas available. If the JWKS endpoint is failing, restore that dependency before restarting all pods.

- Never disable signature, issuer, audience, or expiry validation.
- Never publish private signing-key material in logs, tickets, or chat.
- Do not rotate or revoke signing keys without confirming token overlap and rollback plans.
- Do not delete Kubernetes Secrets to force refreshes.

## Recovery validation

```bash
kubectl -n prod logs deployment/auth-service --since=5m | grep -cE 'kid not found|invalid signature|JWKS cache refresh failed'
curl -fsS https://auth.northstar.example/health/ready
```

Confirm HTTP 401 rate returns to baseline, login success exceeds 99.5%, and every active signing `kid` appears in JWKS.

## Escalation

Page Identity Platform immediately if the authoritative key is missing, private-key exposure is suspected, or failures persist after one controlled rollout. Engage Security for any unauthorized key change.

---

runbook_id: RB-KAFKA-001
title: Kafka Consumer Rebalance Storm and Lag Surge
service: worker-orders
severity: SEV-2
owner: Order Processing
tags: [kafka, rebalance, consumer-lag]
source_url: internal://runbooks/rb-kafka-001
last_verified_at: 2026-09-20
---

# Kafka Consumer Rebalance Storm and Lag Surge

## Purpose

Stabilize the worker-orders consumer group when repeated partition rebalances interrupt processing and cause order-event lag to rise.

## Use this when

- Logs contain `Revoking previously assigned partitions`, `CommitFailedException`, or `REBALANCE_IN_PROGRESS`.
- Consumer lag exceeds 50,000 records or ten minutes.
- Group membership changes more than three times in five minutes.
- Pods restart, fail liveness checks, or exceed `max.poll.interval.ms`.

## Initial checks — read-only

```bash
kubectl -n prod get pods -l app=worker-orders -o wide
kubectl -n prod logs deployment/worker-orders --since=15m | grep -E 'REBALANCE_IN_PROGRESS|CommitFailedException|Revoking previously'
kafka-consumer-groups.sh --bootstrap-server kafka.prod:9092 --group worker-orders --describe
kafka-consumer-groups.sh --bootstrap-server kafka.prod:9092 --group worker-orders --state
kubectl -n prod top pods -l app=worker-orders
```

## Decision points

- If lag is isolated to one partition with a stable group, use RB-KAFKA-002.
- If pods are OOMKilled or CPU-throttled, stabilize resources before changing consumer count.
- If processing time exceeds `max.poll.interval.ms`, reduce batch size or increase the interval through a reviewed deployment.
- If brokers report widespread instability, escalate to the Streaming Platform team.

## Safe mitigation

Freeze autoscaling changes, then restore the last known stable replica count with incident commander approval:

```bash
kubectl -n prod scale deployment/worker-orders --replicas=12
kubectl -n prod rollout status deployment/worker-orders --timeout=10m
```

Change one variable at a time and wait for the group to remain stable for five minutes.

- Never reset offsets to latest merely to reduce displayed lag.
- Never restart every consumer simultaneously.
- Do not increase replicas beyond partition count.
- Do not alter broker metadata or delete consumer groups during an incident.

## Recovery validation

```bash
kafka-consumer-groups.sh --bootstrap-server kafka.prod:9092 --group worker-orders --describe
kubectl -n prod logs deployment/worker-orders --since=5m | grep -c 'REBALANCE_IN_PROGRESS'
```

Confirm no rebalance for ten minutes, lag decreases continuously, and order-processing success remains above 99%.

## Escalation

Page Streaming Platform if broker errors occur, group coordination remains unstable for 15 minutes, or lag threatens the order-processing SLO.

---

runbook_id: RB-ES-001
title: OpenSearch Flood-Stage Disk Watermark Read-Only Block
service: catalog-api
severity: SEV-1
owner: Search Platform
tags: [opensearch, disk, flood-stage]
source_url: internal://runbooks/rb-es-001
last_verified_at: 2026-09-20
---

# OpenSearch Flood-Stage Disk Watermark Read-Only Block

## Purpose

Restore catalog indexing after OpenSearch crosses the flood-stage disk watermark and applies `index.blocks.read_only_allow_delete`.

## Use this when

- catalog-api returns HTTP 500 during indexing or product updates.
- Logs contain `cluster_block_exception` or `FORBIDDEN/12/index read-only / allow delete`.
- Any data node exceeds 95% disk utilization.
- Cluster allocation reports disk-watermark decisions.

## Initial checks — read-only

```bash
curl -fsS https://opensearch.prod/_cluster/health?pretty
curl -fsS 'https://opensearch.prod/_cat/allocation?v&h=node,disk.percent,disk.avail,disk.total'
curl -fsS 'https://opensearch.prod/_cat/indices?v&s=store.size:desc'
curl -fsS 'https://opensearch.prod/_cluster/allocation/explain?pretty'
curl -fsS 'https://opensearch.prod/_all/_settings?filter_path=**.blocks.read_only_allow_delete'
```

## Decision points

- If a node is above 95%, free or add capacity before clearing index blocks.
- If disk is below 90% but allocation is stuck, inspect shard allocation failures.
- If only disposable, policy-managed indices are large, use their approved retention workflow.
- If catalog data integrity is uncertain, pause writes and escalate.

## Safe mitigation

After disk utilization is below 90% on every data node, obtain Search Platform approval and clear the automatically applied block:

```bash
curl -fsS -X PUT https://opensearch.prod/_all/_settings -H 'Content-Type: application/json' -d '{"index.blocks.read_only_allow_delete":null}'
```

Use the approved capacity or index-lifecycle procedure to prevent recurrence.

- Never delete catalog indices, snapshots, or shards ad hoc.
- Never disable disk watermarks.
- Never use wildcard destructive APIs without Search Platform approval.
- Do not clear the block while any node remains above 95%.

## Recovery validation

```bash
curl -fsS https://opensearch.prod/_cluster/health?pretty
curl -fsS 'https://opensearch.prod/_cat/allocation?v&h=node,disk.percent,disk.avail'
curl -fsS 'https://opensearch.prod/_all/_settings?filter_path=**.blocks.read_only_allow_delete'
```

Confirm cluster status is green or accepted yellow, disk is below 90%, indexing succeeds, and catalog-api 5xx rate is below 1%.

## Escalation

Page Search Platform for red cluster health, unassigned primary shards, disk growth after mitigation, or any suspected data loss.

---

runbook_id: RB-DNS-001
title: CoreDNS Throttling and Upstream UDP Resolution Timeouts
service: edge-proxy
severity: SEV-1
owner: Platform Networking
tags: [coredns, dns, timeout]
source_url: internal://runbooks/rb-dns-001
last_verified_at: 2026-09-20
---

# CoreDNS Throttling and Upstream UDP Resolution Timeouts

## Purpose

Restore external API name resolution when CoreDNS is CPU-throttled, overloaded, or timing out against upstream UDP resolvers.

## Use this when

- edge-proxy logs contain `no such host`, `i/o timeout`, or `SERVFAIL`.
- CoreDNS latency p99 exceeds 500 ms or failure rate exceeds 2%.
- CoreDNS CPU throttling exceeds 20%.
- Resolution fails inside pods but succeeds outside the cluster.

## Initial checks — read-only

```bash
kubectl -n kube-system get pods -l k8s-app=kube-dns -o wide
kubectl -n kube-system top pods -l k8s-app=kube-dns
kubectl -n kube-system logs deployment/coredns --since=10m | grep -E 'timeout|SERVFAIL|plugin/errors'
kubectl -n kube-system get configmap coredns -o yaml
kubectl -n prod exec deployment/edge-proxy -- getent hosts api.sendgrid.com
```

## Decision points

- If only one hostname fails, verify the authoritative DNS provider before changing CoreDNS.
- If CoreDNS is throttled, increase capacity through the approved deployment configuration.
- If upstream UDP requests time out, test approved TCP forwarding or engage network operations.
- If failures are node-specific, inspect node networking and conntrack saturation.

## Safe mitigation

With Platform Networking approval, restart CoreDNS one rolling deployment at a time:

```bash
kubectl -n kube-system rollout restart deployment/coredns
kubectl -n kube-system rollout status deployment/coredns --timeout=5m
```

If saturation continues, scale through the reviewed infrastructure configuration rather than an untracked emergency edit.

- Never replace upstream resolvers with public DNS without security approval.
- Never flush node firewall or conntrack state blindly.
- Do not edit the Corefile without validation and rollback.
- Never restart all DNS pods simultaneously.

## Recovery validation

```bash
kubectl -n prod exec deployment/edge-proxy -- getent hosts api.sendgrid.com
kubectl -n kube-system logs deployment/coredns --since=5m | grep -cE 'timeout|SERVFAIL'
```

Confirm resolution success above 99.9%, p99 below 200 ms, and edge-proxy external calls recover.

## Escalation

Page Platform Networking if failures span multiple clusters, upstream resolver health is degraded, or DNS does not stabilize after one rollout.

---

runbook_id: RB-TLS-001
title: Ingress TLS Certificate Expiry and Handshake 525 Errors
service: edge-proxy
severity: SEV-1
owner: Platform Networking
tags: [tls, certificate, ingress]
source_url: internal://runbooks/rb-tls-001
last_verified_at: 2026-09-20
---

# Ingress TLS Certificate Expiry and Handshake 525 Errors

## Purpose

Restore HTTPS traffic when the ingress certificate is expired, not yet valid, mismatched, incomplete, or not reloaded by edge-proxy.

## Use this when

- Clients or CDN report `525 SSL handshake failed`.
- TLS monitoring shows fewer than seven days before expiry.
- `openssl` reports hostname mismatch, expired certificate, or incomplete chain.
- cert-manager Certificate or CertificateRequest is not Ready.

## Initial checks — read-only

```bash
echo | openssl s_client -connect shop.northstar.example:443 -servername shop.northstar.example 2>/dev/null | openssl x509 -noout -subject -issuer -dates -ext subjectAltName
kubectl -n prod get ingress edge-proxy -o yaml
kubectl -n prod get certificate,certificaterequest,order,challenge
kubectl -n prod describe certificate edge-proxy-tls
kubectl -n prod get secret edge-proxy-tls -o jsonpath='{.type}{"\n"}'
```

## Decision points

- If the certificate is expired or lacks the hostname, prioritize renewal or approved rollback.
- If the Secret contains the renewed certificate but ingress serves the old one, reload edge-proxy.
- If ACME validation is failing, resolve DNS or HTTP challenge failures.
- If CDN-to-origin TLS alone fails, verify origin trust and SNI configuration.

## Safe mitigation

After confirming the renewed Secret is valid, restart edge-proxy with incident commander approval:

```bash
kubectl -n prod rollout restart deployment/edge-proxy
kubectl -n prod rollout status deployment/edge-proxy --timeout=10m
```

- Never disable TLS verification or serve plaintext as a workaround.
- Never place private keys in command output, tickets, or chat.
- Do not delete the active TLS Secret before a valid replacement exists.
- Do not bypass certificate hostname validation.

## Recovery validation

```bash
echo | openssl s_client -connect shop.northstar.example:443 -servername shop.northstar.example 2>/dev/null | openssl x509 -noout -dates -ext subjectAltName
curl -fsSI https://shop.northstar.example/health
```

Confirm the full chain is trusted, expiry exceeds 30 days, the hostname is present, and 525 errors fall to zero.

## Escalation

Page Platform Networking and Security if the private key may be compromised, certificate issuance remains blocked, or multiple domains are affected.

---

runbook_id: RB-RATE-001
title: SendGrid 429 Rate-Limit Cascade
service: notification-worker
severity: SEV-2
owner: Messaging Platform
tags: [sendgrid, rate-limit, retry]
source_url: internal://runbooks/rb-rate-001
last_verified_at: 2026-09-20
---

# SendGrid 429 Rate-Limit Cascade

## Purpose

Prevent retry amplification and restore email delivery when SendGrid returns HTTP 429 responses to notification-worker.

## Use this when

- Logs contain `HTTP 429 Too Many Requests` from SendGrid.
- Email queue age exceeds five minutes.
- Retry volume grows faster than successful sends.
- SendGrid response headers show exhausted rate limits.

## Initial checks — read-only

```bash
kubectl -n prod logs deployment/notification-worker --since=15m | grep -E '429|Too Many Requests|Retry-After'
kubectl -n prod get deployment notification-worker -o yaml | grep -E 'CONCURRENCY|RETRY|SENDGRID'
kubectl -n prod top pods -l app=notification-worker
kubectl -n prod get hpa notification-worker
```

## Decision points

- If all SendGrid requests return 429, honor `Retry-After` and reduce concurrency.
- If one API key or message type is affected, isolate that traffic without stopping transactional email.
- If queue growth threatens retention, engage Messaging Platform to expand safe buffering.
- If 401 or 403 responses occur instead, investigate credentials rather than rate limits.

## Safe mitigation

With Messaging Platform approval, reduce worker concurrency to the documented safe level:

```bash
kubectl -n prod set env deployment/notification-worker SENDGRID_CONCURRENCY=10
kubectl -n prod rollout status deployment/notification-worker --timeout=10m
```

Ensure retries use exponential backoff with jitter and respect `Retry-After`.

- Never retry 429 responses in a tight loop.
- Never rotate API keys solely to evade provider limits.
- Do not drop queued transactional emails.
- Do not expose recipient addresses or API keys in diagnostics.

## Recovery validation

```bash
kubectl -n prod logs deployment/notification-worker --since=5m | grep -cE '429|Too Many Requests'
kubectl -n prod get pods -l app=notification-worker
```

Confirm 429 rate is below 0.1%, queue age decreases, and delivery success returns above 99%.

## Escalation

Page Messaging Platform if throttling persists for 30 minutes, queue retention is at risk, or SendGrid reports an account-wide restriction.

---

runbook_id: RB-PG-003
title: PostgreSQL XID Wraparound Risk and Autovacuum Starvation
service: postgres-primary
severity: SEV-1
owner: Database Reliability
tags: [postgresql, xid, autovacuum]
source_url: internal://runbooks/rb-pg-003
last_verified_at: 2026-09-20
---

# PostgreSQL XID Wraparound Risk and Autovacuum Starvation

## Purpose

Prevent PostgreSQL transaction ID wraparound and emergency shutdown when frozen XID age rises because autovacuum cannot process high-churn tables.

## Use this when

- `age(datfrozenxid)` exceeds 1.5 billion.
- Logs warn `database must be vacuumed within ... transactions`.
- Autovacuum workers are blocked or absent on high-churn tables.
- Long-running transactions prevent vacuum progress.

## Initial checks — read-only

```sql
SELECT datname, age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;

SELECT n.nspname, c.relname, age(c.relfrozenxid) AS xid_age,
       s.n_dead_tup, s.last_autovacuum
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
WHERE c.relkind = 'r'
ORDER BY xid_age DESC
LIMIT 20;

SELECT pid, usename, state, xact_start, wait_event_type, wait_event, query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

## Decision points

- At 1.8 billion XIDs or a wraparound warning, treat the incident as immediate SEV-1.
- If a long transaction blocks vacuum, contact its owner before cancellation.
- If autovacuum workers are saturated, tune only through an approved database change.
- If storage is insufficient for vacuum progress, add capacity before proceeding.

## Safe mitigation

With Database Reliability and incident commander approval, freeze the highest-risk identified table:

```sql
VACUUM (FREEZE, VERBOSE, ANALYZE) public.order_events;
```

Run one high-risk table at a time and monitor I/O, replication lag, and application latency.

- Never run `VACUUM FULL` during live incident response.
- Never reset transaction IDs or edit PostgreSQL control data.
- Do not terminate unknown transactions without owner and incident commander approval.
- Never disable autovacuum globally.

## Recovery validation

```sql
SELECT datname, age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;

SELECT age(relfrozenxid) AS xid_age
FROM pg_class
WHERE oid = 'public.order_events'::regclass;
```

Confirm XID age is falling, autovacuum is progressing, replication lag remains within SLO, and no wraparound warnings recur.

## Escalation

Page Database Reliability immediately at 1.8 billion XIDs, when PostgreSQL enters wraparound protection, or when vacuum cannot progress safely.

---

runbook_id: RB-REDIS-002
title: Redis Lua Script Lockup and Command Queueing
service: redis-cache
severity: SEV-1
owner: Cache Platform
tags: [redis, lua, latency]
source_url: internal://runbooks/rb-redis-002
last_verified_at: 2026-09-20
---

# Redis Lua Script Lockup and Command Queueing

## Purpose

Restore Redis responsiveness when a long-running Lua script blocks the single execution thread and causes command queues and latency spikes.

## Use this when

- Logs or clients report `BUSY Redis is busy running a script`.
- Redis command latency exceeds 500 ms while CPU is saturated.
- `SLOWLOG` identifies `EVAL` or `EVALSHA`.
- `blocked_clients` or connected-client queues rise rapidly.

## Initial checks — read-only

```bash
redis-cli -h redis-cache.prod INFO clients
redis-cli -h redis-cache.prod INFO commandstats
redis-cli -h redis-cache.prod SLOWLOG GET 20
redis-cli -h redis-cache.prod CLIENT LIST | head -50
redis-cli -h redis-cache.prod LATENCY LATEST
```

## Decision points

- If the running script has not written data, `SCRIPT KILL` can terminate it safely.
- If the script has performed writes, Redis will reject `SCRIPT KILL`; escalate before failover.
- If latency is not associated with Lua, investigate memory, network, or persistence pressure.
- Identify and disable the application call path before the script is retried.

## Safe mitigation

After pausing the offending caller and obtaining Cache Platform approval, attempt:

```bash
redis-cli -h redis-cache.prod SCRIPT KILL
```

If Redis reports that writes already occurred, stop and escalate; do not force process termination.

- Never run `FLUSHALL`, `FLUSHDB`, or unreviewed `DEBUG` commands.
- Never kill the Redis process to interrupt a script.
- Do not fail over after a write-producing script without assessing consistency.
- Do not rerun the offending script in production.

## Recovery validation

```bash
redis-cli -h redis-cache.prod PING
redis-cli -h redis-cache.prod INFO clients
redis-cli -h redis-cache.prod LATENCY LATEST
redis-cli -h redis-cache.prod SLOWLOG GET 5
```

Confirm `PONG`, command latency below 10 ms, queues drain, and no new `BUSY` errors occur for ten minutes.

## Escalation

Page Cache Platform if `SCRIPT KILL` is rejected, replication health changes, or the script immediately recurs.

---

runbook_id: RB-K8S-002
title: Kubernetes Worker Ephemeral Storage Exhaustion
service: worker-orders
severity: SEV-1
owner: Compute Platform
tags: [kubernetes, ephemeral-storage, diskpressure]
source_url: internal://runbooks/rb-k8s-002
last_verified_at: 2026-09-20
---

# Kubernetes Worker Ephemeral Storage Exhaustion

## Purpose

Restore worker-orders capacity when node ephemeral storage exhaustion triggers DiskPressure, pod eviction, or container write failures.

## Use this when

- Nodes report `DiskPressure=True`.
- Pods are evicted with `The node was low on resource: ephemeral-storage`.
- Containers report `no space left on device`.
- Image filesystem or node filesystem utilization exceeds 90%.

## Initial checks — read-only

```bash
kubectl get nodes
kubectl describe nodes | grep -A8 -B3 -E 'DiskPressure|ephemeral-storage'
kubectl -n prod get pods -l app=worker-orders -o wide
kubectl -n prod describe pods -l app=worker-orders | grep -E 'Evicted|ephemeral-storage|no space'
kubectl get events --all-namespaces --sort-by=.lastTimestamp | tail -100
```

## Decision points

- If one node is affected, cordon it before investigating local disk consumers.
- If all nodes are affected, add capacity and inspect workload-wide logging or temporary-file growth.
- If a pod exceeds its configured limit, fix the workload before rescheduling it repeatedly.
- Preserve forensic evidence if unexpected files may indicate compromise.

## Safe mitigation

With Compute Platform approval, stop new scheduling on the affected node:

```bash
kubectl cordon <affected-node>
```

After capacity is available, drain it through the approved disruption procedure:

```bash
kubectl drain <affected-node> --ignore-daemonsets --delete-emptydir-data --grace-period=60
```

- Never run recursive deletion commands on node filesystems without identifying ownership.
- Never drain multiple production nodes simultaneously without capacity confirmation.
- Do not delete container runtime state manually.
- Do not uncordon until DiskPressure is cleared.

## Recovery validation

```bash
kubectl get node <affected-node> -o jsonpath='{.status.conditions[?(@.type=="DiskPressure")].status}{"\n"}'
kubectl -n prod get pods -l app=worker-orders
kubectl get events --all-namespaces --sort-by=.lastTimestamp | tail -30
```

Confirm DiskPressure is false, evictions stop, replacement pods are Ready, and order lag decreases.

## Escalation

Page Compute Platform if multiple nodes cross 90%, drain is blocked by disruption budgets, or disk usage cannot be attributed safely.

---

runbook_id: RB-PAY-001
title: Payment Idempotency Lock Deadlock During Flash Sale
service: checkout-api
severity: SEV-1
owner: Payments Platform
tags: [payments, deadlock, idempotency]
source_url: internal://runbooks/rb-pay-001
last_verified_at: 2026-09-20
---

# Payment Idempotency Lock Deadlock During Flash Sale

## Purpose

Restore payment capture when concurrent requests deadlock on the idempotency table during high-volume checkout traffic while preserving exactly-once behavior.

## Use this when

- checkout-api logs contain `deadlock detected` involving the idempotency table.
- Payment capture latency exceeds two seconds during a traffic spike.
- PostgreSQL reports sessions waiting on transaction or tuple locks.
- Retries increase while completed captures stop advancing.

## Initial checks — read-only

```bash
kubectl -n prod logs deployment/checkout-api --since=15m | grep -E 'deadlock detected|idempotency|payment capture'
```

```sql
SELECT pid, usename, state, wait_event_type, wait_event, xact_start, query
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;

SELECT blocked.pid AS blocked_pid, blocker.pid AS blocker_pid,
       blocked.query AS blocked_query, blocker.query AS blocker_query
FROM pg_stat_activity blocked
JOIN pg_locks bl ON bl.pid = blocked.pid AND NOT bl.granted
JOIN pg_locks kl ON kl.locktype = bl.locktype AND kl.granted
JOIN pg_stat_activity blocker ON blocker.pid = kl.pid;
```

## Decision points

- If PostgreSQL is resolving short deadlocks automatically, reduce traffic pressure and fix retry jitter.
- If one stale session blocks many captures, validate its business state before cancellation.
- If duplicate provider captures are possible, pause mutation and reconcile before resuming.
- If the deadlock involves migration DDL, use RB-DEPLOY-001.

## Safe mitigation

With Payments Platform and incident commander approval, cancel only the verified stale blocker:

```sql
SELECT pg_cancel_backend(<verified_blocker_pid>);
```

Preserve idempotency enforcement and use bounded retries with jitter.

- Never delete or truncate idempotency records.
- Never disable uniqueness constraints or reuse idempotency keys.
- Do not terminate a backend before confirming payment state.
- Never replay capture requests without provider reconciliation.

## Recovery validation

```sql
SELECT count(*) AS waiting_sessions
FROM pg_stat_activity
WHERE wait_event_type = 'Lock';
```

Confirm lock waits return to baseline, capture success exceeds 99%, p95 latency is below 750 ms, and no duplicate captures occurred.

## Escalation

Page Payments Platform and Database Reliability for unresolved blockers, possible duplicate charges, or deadlocks continuing after traffic normalization.

---

runbook_id: RB-KAFKA-002
title: Kafka Poison-Pill Message Blocking Order Ingestion
service: worker-orders
severity: SEV-1
owner: Order Processing
tags: [kafka, poison-pill, partition]
source_url: internal://runbooks/rb-kafka-002
last_verified_at: 2026-09-20
---

# Kafka Poison-Pill Message Blocking Order Ingestion

## Purpose

Resume a blocked Kafka partition when one malformed or incompatible order event repeatedly fails and prevents offset advancement.

## Use this when

- One partition's lag rises while other partitions remain healthy.
- Logs repeatedly show the same topic, partition, and offset.
- Errors include `SerializationException`, schema validation failure, or deterministic handler failure.
- Consumer membership is stable and no rebalance storm is present.

## Initial checks — read-only

```bash
kafka-consumer-groups.sh --bootstrap-server kafka.prod:9092 --group worker-orders --describe
kubectl -n prod logs deployment/worker-orders --since=15m | grep -E 'SerializationException|schema validation|partition|offset'
kafka-console-consumer.sh --bootstrap-server kafka.prod:9092 --topic orders.v1 --partition <partition> --offset <offset> --max-messages 1
```

## Decision points

- If many partitions lag and rebalances recur, use RB-KAFKA-001.
- If the message can be processed after a backward-compatible code fix, deploy the fix rather than skipping it.
- If it cannot be processed, preserve the raw record and publish it to the approved dead-letter topic.
- Confirm the exact current group offset before any offset mutation.

## Safe mitigation

After archiving the raw record to the DLQ and obtaining incident commander approval, advance only the affected partition:

```bash
kafka-consumer-groups.sh --bootstrap-server kafka.prod:9092 --group worker-orders --topic orders.v1:<partition> --reset-offsets --to-offset <next_offset> --execute
```

- Never reset the entire consumer group.
- Never use `--to-latest` to hide lag.
- Do not skip a record without durable DLQ evidence and incident approval.
- Never print customer-sensitive payload fields into tickets or chat.

## Recovery validation

```bash
kafka-consumer-groups.sh --bootstrap-server kafka.prod:9092 --group worker-orders --describe
kubectl -n prod logs deployment/worker-orders --since=5m | grep -E 'SerializationException|schema validation'
```

Confirm the affected partition advances, lag decreases, downstream order counts reconcile, and the DLQ contains the skipped record.

## Escalation

Page Order Processing and Streaming Platform if multiple poison records appear, offset ownership is uncertain, or reconciliation fails.

---

runbook_id: RB-SEC-001
title: Credential Stuffing CPU and HTTP 401 Surge
service: auth-service
severity: SEV-1
owner: Security Operations
tags: [security, credential-stuffing, waf]
source_url: internal://runbooks/rb-sec-001
last_verified_at: 2026-09-20
---

# Credential Stuffing CPU and HTTP 401 Surge

## Purpose

Protect authentication availability and customer accounts during automated credential-stuffing traffic that drives abnormal CPU usage and failed-login volume.

## Use this when

- HTTP 401 responses exceed 20% and auth-service CPU exceeds 80%.
- Failed logins originate from distributed IPs or repeated account lists.
- WAF or identity telemetry indicates automation.
- Legitimate login latency or success rate degrades.

## Initial checks — read-only

```bash
kubectl -n prod top pods -l app=auth-service
kubectl -n prod logs deployment/auth-service --since=10m | grep -E '401|invalid credentials|rate limit' | head -200
kubectl -n prod get hpa auth-service
aws wafv2 get-web-acl --scope REGIONAL --id <web-acl-id> --name northstar-auth --region us-east-1
aws wafv2 get-sampled-requests --web-acl-arn <web-acl-arn> --rule-metric-name LoginRateLimit --scope REGIONAL --time-window StartTime=<start>,EndTime=<end> --max-items 100 --region us-east-1
```

## Decision points

- If failures correlate with a deployment or JWKS errors, use RB-AUTH-001.
- If traffic shows automated concentration, apply the approved WAF rate-limit profile.
- If account takeover is confirmed, trigger Security's customer-protection procedure.
- If resource saturation persists after filtering, add temporary application capacity.

## Safe mitigation

With Security Operations approval, apply the pre-reviewed credential-stuffing Web ACL:

```bash
aws wafv2 update-web-acl --scope REGIONAL --id <web-acl-id> --name northstar-auth --region us-east-1 --lock-token <lock-token> --cli-input-json file://approved-credential-stuffing-web-acl.json
```

Monitor false positives and preserve sampled-request evidence.

- Never log passwords, authorization headers, session tokens, or full credential payloads.
- Never block entire countries or major networks without Security approval.
- Do not disable authentication or account lockout controls.
- Do not publicly identify suspected victims.

## Recovery validation

```bash
kubectl -n prod top pods -l app=auth-service
kubectl -n prod logs deployment/auth-service --since=5m | grep -c 'invalid credentials'
```

Confirm CPU falls below 60%, legitimate login success exceeds 99%, latency returns to SLO, and attack traffic is constrained.

## Escalation

Page Security Operations immediately for confirmed account takeover, data exposure, rapidly changing attack sources, or ineffective WAF controls.

---

runbook_id: RB-S3-001
title: Invoice Upload Bucket Policy Permission Denied
service: notification-worker
severity: SEV-2
owner: Cloud Platform
tags: [s3, iam, invoices]
source_url: internal://runbooks/rb-s3-001
last_verified_at: 2026-09-20
---

# Invoice Upload Bucket Policy Permission Denied

## Purpose

Restore invoice uploads when notification-worker loses permission to write objects to the invoice S3 bucket.

## Use this when

- Logs contain `AccessDenied` for `s3:PutObject`.
- Invoice generation succeeds but object upload fails.
- Failures start after IAM role, bucket policy, KMS key, or service-account changes.
- AWS request IDs show consistent authorization failures.

## Initial checks — read-only

```bash
kubectl -n prod logs deployment/notification-worker --since=15m | grep -E 'AccessDenied|PutObject|invoice'
kubectl -n prod get serviceaccount notification-worker -o yaml
aws sts get-caller-identity
aws s3api get-bucket-policy --bucket northstar-invoices
aws s3api get-public-access-block --bucket northstar-invoices
aws iam simulate-principal-policy --policy-source-arn <notification-worker-role-arn> --action-names s3:PutObject kms:Encrypt --resource-arns arn:aws:s3:::northstar-invoices/test-object
```

## Decision points

- If `s3:PutObject` is denied, compare the role and bucket policy with the approved baseline.
- If `kms:Encrypt` is denied, inspect the KMS key policy rather than widening S3 access.
- If the caller identity is unexpected, fix workload identity before policy changes.
- If only one prefix fails, verify resource ARN and condition matching.

## Safe mitigation

After Cloud Platform and Security approval, restore the reviewed bucket policy:

```bash
aws s3api put-bucket-policy --bucket northstar-invoices --policy file://approved-invoice-policy.json
```

Prefer correcting the narrow role, prefix, or KMS permission over granting broad bucket access.

- Never grant public access or use wildcard principals.
- Never add `s3:*` or `kms:*` as a shortcut.
- Do not disable encryption requirements.
- Never upload real invoice data as a diagnostic test.

## Recovery validation

```bash
aws iam simulate-principal-policy --policy-source-arn <notification-worker-role-arn> --action-names s3:PutObject kms:Encrypt --resource-arns arn:aws:s3:::northstar-invoices/test-object
kubectl -n prod logs deployment/notification-worker --since=5m | grep -c 'AccessDenied'
```

Confirm policy simulation allows only required actions, a synthetic invoice upload succeeds, and the failed queue drains.

## Escalation

Page Cloud Platform and Security if the policy changed unexpectedly, KMS access remains denied, or broader unauthorized access is detected.

---

runbook_id: RB-DEPLOY-001
title: Database Migration Lock Deadlock During Zero-Downtime Deploy
service: checkout-api
severity: SEV-1
owner: Release Engineering
tags: [deployment, migration, postgresql]
source_url: internal://runbooks/rb-deploy-001
last_verified_at: 2026-09-20
---

# Database Migration Lock Deadlock During Zero-Downtime Deploy

## Purpose

Restore checkout availability when a database migration waits on or deadlocks with live transactions during a zero-downtime deployment.

## Use this when

- Deployment stalls while a migration waits for `AccessExclusiveLock`.
- PostgreSQL logs contain `deadlock detected` involving DDL.
- checkout-api latency rises immediately after a migration starts.
- Old and new application versions are simultaneously active with incompatible schema expectations.

## Initial checks — read-only

```bash
kubectl -n prod rollout status deployment/checkout-api --timeout=30s
kubectl -n prod logs job/checkout-db-migrate --since=30m
```

```sql
SELECT pid, usename, application_name, state, wait_event_type, wait_event,
       xact_start, query_start, query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY query_start;

SELECT l.pid, l.locktype, l.mode, l.granted, c.relname
FROM pg_locks l
LEFT JOIN pg_class c ON c.oid = l.relation
ORDER BY l.granted, l.pid;
```

## Decision points

- If migration DDL is waiting without blocking production, cancel the migration and reassess.
- If the migration blocks checkout traffic, stop rollout progression and prioritize restoring service.
- If schema changes are not backward compatible, use the documented application rollback plan.
- If payment idempotency locks are involved without DDL, use RB-PAY-001.

## Safe mitigation

With Release Engineering and Database Reliability approval, cancel only the verified migration backend:

```sql
SELECT pg_cancel_backend(<migration_pid>);
```

Pause the deployment and revert to the last schema-compatible application revision through the release pipeline.

- Never drop columns, tables, constraints, or indexes during emergency response.
- Never use `pg_terminate_backend` before a graceful cancellation attempt and approval.
- Do not mark a failed migration as complete manually.
- Never rerun non-idempotent migration steps without reviewing their state.

## Recovery validation

```sql
SELECT pid, application_name, wait_event_type, wait_event, query
FROM pg_stat_activity
WHERE wait_event_type = 'Lock';
```

```bash
kubectl -n prod rollout status deployment/checkout-api --timeout=10m
curl -fsS https://checkout-api.prod/health/ready
```

Confirm blocking locks are gone, the migration is stopped or completed safely, checkout error rate is below 1%, and schema compatibility is verified.

## Escalation

Page Release Engineering and Database Reliability if cancellation fails, DDL partially applied, rollback is incompatible, or checkout remains impaired.