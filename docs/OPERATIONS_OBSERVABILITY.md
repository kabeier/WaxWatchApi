# Operations Observability, Dashboards, Alerts, and Runbook

## Key telemetry

### HTTP/API telemetry
- `waxwatch_request_latency_seconds` (histogram)
  - Labels: `method`, `path`, `status_code`
  - Use this for p50/p90/p95 API latency and error-rate splits.

### Provider telemetry
- `waxwatch_provider_call_results_total` (counter)
  - Labels: `provider`, `outcome`, `status_code`
  - `outcome` is one of `success`, `error`, `unknown`.

### Scheduler telemetry
- `waxwatch_scheduler_rule_outcomes_total` (counter)
  - Labels: `outcome` (`success` or `failed`)
- `waxwatch_scheduler_runs_total` (counter)
  - Labels: `outcome` (`success` if no failed rules in that polling run; else `failed`)

### Error reporting
- Optional Sentry integration is enabled only when:
  - `SENTRY_DSN` is set, and
  - `ENVIRONMENT` is in `SENTRY_ENABLED_ENVIRONMENTS` (default: `staging,prod`).
- Each error report includes `request_id` for correlation with logs.

## Suggested dashboards

### 1) API health dashboard
- Request rate by endpoint (`sum(rate(waxwatch_request_latency_seconds_count[5m])) by (path, method)`).
- Latency p95 by endpoint (`histogram_quantile(0.95, sum(rate(waxwatch_request_latency_seconds_bucket[5m])) by (le, path, method))`).
- 5xx rate by endpoint (`sum(rate(waxwatch_request_latency_seconds_count{status_code=~"5.."}[5m])) by (path)`).

### 2) Provider reliability dashboard
- Provider call volume (`sum(rate(waxwatch_provider_call_results_total[5m])) by (provider, outcome)`).
- Provider error ratio (`sum(rate(waxwatch_provider_call_results_total{outcome="error"}[15m])) by (provider) / sum(rate(waxwatch_provider_call_results_total[15m])) by (provider)`).
- Status-code breakdown (`sum(rate(waxwatch_provider_call_results_total[15m])) by (provider, status_code)`).

### 3) Scheduler health dashboard
- Scheduler run status (`sum(rate(waxwatch_scheduler_runs_total[10m])) by (outcome)`).
- Rule outcome failure ratio (`sum(rate(waxwatch_scheduler_rule_outcomes_total{outcome="failed"}[10m])) / sum(rate(waxwatch_scheduler_rule_outcomes_total[10m]))`).

### 4) SLO compliance dashboard
- API p95 latency by endpoint category (read/query/write).
- Provider error budget burn by provider (`1 - success_ratio`) for 15m/1h/24h windows.
- Scheduler freshness lag (`execution_started_at - next_run_at`) p95 and max.
- Notification delivery lag (`notification_sent_at - event_created_at`) p95 and max.

## Concrete SLO targets

### API latency SLO (rolling 28d, per endpoint category)
- **Read endpoints** (`GET` collection/detail): p95 `< 400ms`.
- **Query/search endpoints** (watch/search fan-out): p95 `< 900ms`.
- **Write endpoints** (`POST/PATCH/DELETE`): p95 `< 700ms`.
- **Availability guardrail**: 5xx ratio `< 1%` per category.

If category labels are not available in metrics, maintain a static route map in dashboard config and aggregate by the mapped category.

### Provider reliability SLO + error budget (rolling 28d, per provider)
- Success ratio target: `>= 99.0%` for provider calls (`outcome="success"`).
- Error budget: `<= 1.0%` failed calls per provider over 28d.
- Fast-burn protection windows:
  - 1h window should remain `< 3.0%` errors.
  - 6h window should remain `< 2.0%` errors.
  - 24h window should remain `< 1.5%` errors.

### Scheduler freshness SLO (rolling 7d)
- Freshness lag target: p95 of `execution_started_at - next_run_at` `< 60s`.
- Hard limit: max lag `< 180s`.

### Notification delivery lag SLO (rolling 7d)
- Delivery lag target: p95 of `notification_sent_at - event_created_at` `< 45s`.
- Hard limit: p99 `< 120s`.

For scheduler and notification lag SLOs, add/maintain explicit instrumentation if these timestamps are not yet exposed as metrics.

## Suggested alert rules

1. **API elevated latency (warning/critical by endpoint category)**
   - Read endpoints: p95 `> 500ms` for 10m (warning), `> 800ms` for 10m (critical).
   - Query/search endpoints: p95 `> 1.1s` for 10m (warning), `> 1.5s` for 10m (critical).
   - Write endpoints: p95 `> 850ms` for 10m (warning), `> 1.2s` for 10m (critical).

2. **API elevated 5xx rate (warning/critical)**
   - `5xx_count / total_count > 0.02` for 10m (warning).
   - `5xx_count / total_count > 0.05` for 10m (critical).

3. **Provider degradation / error-budget burn (warning/critical per provider)**
   - Error ratio `> 0.03` for 1h (warning; burns 3x 28d budget).
   - Error ratio `> 0.05` for 1h (critical; burns 5x 28d budget).
   - Error ratio `> 0.02` for 6h (warning).
   - Error ratio `> 0.03` for 6h (critical).

4. **Scheduler instability (critical)**
   - Scheduler run failures observed for 3 consecutive intervals, or
   - Rule failure ratio `> 0.25` for 15m.

5. **No scheduler activity (critical)**
   - `increase(waxwatch_scheduler_runs_total[15m]) == 0`.

6. **Scheduler freshness breach (warning/critical)**
   - p95 freshness lag `> 60s` for 10m (warning).
   - max freshness lag `> 180s` for 10m (critical).

7. **Notification delivery lag breach (warning/critical)**
   - p95 delivery lag `> 45s` for 10m (warning).
   - p99 delivery lag `> 120s` for 10m (critical).

## Runbook notes

### Failure class: API latency spike
1. Check API dashboard (top endpoints by p95).
2. Determine whether SLO breach is read/query/write category specific.
3. Correlate with provider errors and DB readiness (`/readyz`).
4. Compare current 10m performance against 28d SLO trend to estimate budget burn rate.
5. If category p95 exceeds critical threshold for >10m, page on-call and start incident channel.
6. Inspect logs for matching `request_id` and slow-path routes.
7. Mitigate:
   - lower fan-out/providers on heavy queries,
   - scale API workers,
   - reduce expensive query limits.
8. Exit criteria: category p95 back under SLO target for 30m and 5xx ratio < 1%.

### Failure class: Provider outage / throttling
1. Identify impacted provider via error ratio and status-code spikes.
2. Inspect provider-specific metadata in persisted provider request logs.
3. Confirm retries/backoff behavior and upstream rate-limit headers.
4. Mitigate:
   - temporary provider disablement (if supported),
   - reduce polling/search frequency,
   - contact provider support for sustained 5xx/429 rates.
5. Track remaining 28d error budget for the provider; if >50% consumed, require feature-owner sign-off before re-enabling full traffic.
6. Exit criteria: provider error ratio below 1.5% for 24h window and below 3% for 1h window.

### Failure class: Scheduler failure loop
1. Check scheduler run and rule outcome counters.
2. Inspect worker logs for exception type and impacted `rule_id`.
3. Validate database connectivity and queue health.
4. Mitigate:
   - restart scheduler worker,
   - pause problematic rules,
   - temporarily increase poll interval to reduce load.
5. Measure freshness lag while recovering; if max lag approaches 180s, temporarily shed non-critical rules.
6. Exit criteria: p95 freshness lag < 60s and max lag < 180s for 30m.

### Failure class: Notification backlog / delivery lag
1. Check notification lag dashboard (p95/p99 and queue depth).
2. Confirm downstream provider/channel health (email/push/webhook).
3. Inspect worker concurrency, retry queues, and dead-letter volumes.
4. Mitigate:
   - increase notification worker concurrency,
   - prioritize high-severity notifications,
   - temporarily pause low-priority digests/batches.
5. Exit criteria: p95 lag < 45s and p99 lag < 120s for 30m.

### Failure class: Error burst in Sentry
1. Group by issue fingerprint and release/environment.
2. Use `request_id` tag to correlate a Sentry event with API logs.
3. Roll back recent deploy if API or provider error budget burn indicates likely 28d SLO violation.
4. Add/adjust alert thresholds if noise from known transient failures.

## Operations checklist (SLO-aligned)

- [ ] Dashboards show SLO status for API latency, provider error budgets, scheduler freshness, and notification lag.
- [ ] Alert thresholds configured exactly to warning/critical values listed above.
- [ ] On-call paging policy wired to all critical alerts.
- [ ] Runbook links embedded in each alert with the matching failure class section.
- [ ] Weekly review includes 28d API/provider budget consumption and 7d scheduler/notification lag compliance.
