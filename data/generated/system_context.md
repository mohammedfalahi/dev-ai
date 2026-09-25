# Northstar Commerce — Production Context

## Purpose

Northstar Commerce is a fictional but operationally realistic SaaS company that
runs an online checkout and order-processing platform. This corpus is synthetic;
no real customer, credential, or company data is included.

## Service catalog

| Service | Tier | Owner | Primary responsibility | Dependencies |
|---|---:|---|---|---|
| `checkout-api` | 1 | Payments Platform | Create and validate checkouts | PostgreSQL, Redis, Stripe |
| `catalog-api` | 2 | Commerce Platform | Serve product and price data | PostgreSQL replica, Redis |
| `worker-orders` | 1 | Commerce Platform | Process order jobs asynchronously | PostgreSQL, Redis |
| `notification-worker` | 2 | Platform | Send customer notifications | Redis, SendGrid |
| `edge-proxy` | 1 | Platform | TLS termination and upstream routing | Kubernetes services |

Production runs in a Kubernetes cluster using the `production` namespace. The
primary relational database is `postgres-primary`; read-heavy catalog traffic
uses `postgres-replica`. Redis is used for cache entries and queue coordination.

## Request and order flow

1. `edge-proxy` terminates TLS and routes `/v1/checkout` to `checkout-api`.
2. `checkout-api` reads product data from Redis or PostgreSQL and writes the
   order transaction to `postgres-primary`.
3. The API publishes an order job to Redis.
4. `worker-orders` consumes the job, updates order state, and emits the Stripe
   webhook reconciliation event.
5. `notification-worker` sends the customer confirmation email.

## Operating targets

- Tier 1 availability target: 99.9% monthly.
- Checkout p95 latency target: below 500 ms.
- Page Payments Primary when checkout 5xx exceeds 2% for five minutes.
- Page Database Primary when PostgreSQL connection utilization exceeds 85% for
  ten minutes or when the primary health check fails twice.
- Page Platform when the edge proxy returns upstream 502s above 3% for five
  minutes.
- Webhook backlog is considered at risk when the oldest unprocessed event is
  older than ten minutes.

## Observability and deployment

Prometheus stores metrics, Loki stores logs, and OpenTelemetry supplies trace
IDs. Grafana dashboards use the service name as the primary filter. Deployments
are made by GitHub Actions using Kubernetes rolling updates. A deployment record
contains the version, commit SHA, author, and start time.

The normal incident evidence sources are alert payloads, application logs,
metrics, traces, deployment events, Kubernetes events, database activity, and
webhook delivery records.

## Severity and ownership

- **SEV-1:** customer checkout or order processing is broadly unavailable.
- **SEV-2:** material degradation with a documented workaround.
- **SEV-3:** limited impact or an internal reliability problem.

The fictional escalation contacts are:

- Priya Nair — Payments Primary
- Mateo Silva — Database Platform
- Linh Tran — Commerce Platform
- Jordan Brooks — Platform On Call

## Safety rules

Read-only inspection is allowed during investigation. Mutating actions require
an explicit approval recorded in the incident. The MVP does not execute Tier 2
destructive operations; it only proposes a verified action and records the
approval state.
