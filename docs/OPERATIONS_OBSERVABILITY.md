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

## Suggested alert rules

1. **API elevated latency (warning/critical)**
   - p95 `> 2.0s` for 10m (warning)
   - p95 `> 4.0s` for 10m (critical)

2. **API elevated 5xx rate (critical)**
   - `5xx_count / total_count > 0.05` for 10m.

3. **Provider degradation (warning/critical per provider)**
   - Provider error ratio `> 0.10` for 15m (warning)
   - Provider error ratio `> 0.25` for 15m (critical)

4. **Scheduler instability (critical)**
   - Scheduler run failures observed for 3 consecutive intervals, or
   - Rule failure ratio `> 0.25` for 15m.

5. **No scheduler activity (critical)**
   - `increase(waxwatch_scheduler_runs_total[15m]) == 0`.

## Runbook notes

### Failure class: API latency spike
1. Check API dashboard (top endpoints by p95).
2. Correlate with provider errors and DB readiness (`/readyz`).
3. Inspect logs for matching `request_id` and slow-path routes.
4. Mitigate:
   - lower fan-out/providers on heavy queries,
   - scale API workers,
   - reduce expensive query limits.

### Failure class: Provider outage / throttling
1. Identify impacted provider via error ratio and status-code spikes.
2. Inspect provider-specific metadata in persisted provider request logs.
3. Confirm retries/backoff behavior and upstream rate-limit headers.
4. Mitigate:
   - temporary provider disablement (if supported),
   - reduce polling/search frequency,
   - contact provider support for sustained 5xx/429 rates.

### Failure class: Scheduler failure loop
1. Check scheduler run and rule outcome counters.
2. Inspect worker logs for exception type and impacted `rule_id`.
3. Validate database connectivity and queue health.
4. Mitigate:
   - restart scheduler worker,
   - pause problematic rules,
   - temporarily increase poll interval to reduce load.

### Failure class: Error burst in Sentry
1. Group by issue fingerprint and release/environment.
2. Use `request_id` tag to correlate a Sentry event with API logs.
3. Roll back recent deploy if error budget is consumed.
4. Add/adjust alert thresholds if noise from known transient failures.
