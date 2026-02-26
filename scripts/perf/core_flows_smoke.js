import http from 'k6/http';
import { check, fail, sleep } from 'k6';

const baseUrl = (__ENV.PERF_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const token = __ENV.PERF_BEARER_TOKEN || '';
const listPath = __ENV.PERF_LIST_PATH || '/api/watch-rules?limit=20';
const releasesListPath = __ENV.PERF_RELEASES_LIST_PATH || '/api/watch-releases?limit=20';
const searchPath = __ENV.PERF_SEARCH_PATH || '/api/search';
const ruleRunPathTemplate = __ENV.PERF_RULE_RUN_PATH || '/api/dev/rules/{rule_id}/run?limit=20';
const ruleId = __ENV.PERF_RULE_ID || '';

const searchPayload = JSON.stringify({
  keywords: (__ENV.PERF_SEARCH_KEYWORDS || 'house,techno').split(',').map((v) => v.trim()).filter(Boolean),
  providers: (__ENV.PERF_SEARCH_PROVIDERS || 'discogs').split(',').map((v) => v.trim()).filter(Boolean),
  page: Number(__ENV.PERF_SEARCH_PAGE || '1'),
  page_size: Number(__ENV.PERF_SEARCH_PAGE_SIZE || '10'),
});

const scenarioVus = Number(__ENV.PERF_VUS || '2');
const scenarioDuration = __ENV.PERF_DURATION || '30s';
const ruleScenarioEnabled = (__ENV.PERF_ENABLE_RULE_RUN || '1') === '1';

export const options = {
  scenarios: {
    authenticated_list_endpoints: {
      executor: 'constant-vus',
      vus: scenarioVus,
      duration: scenarioDuration,
      exec: 'authenticatedListEndpoints',
      tags: { flow: 'auth_list' },
    },
    rule_polling_task_path: {
      executor: 'constant-vus',
      vus: scenarioVus,
      duration: scenarioDuration,
      exec: 'rulePollingTaskPath',
      tags: { flow: 'rule_poll' },
      startTime: '1s',
    },
    provider_request_logging_write_path: {
      executor: 'constant-vus',
      vus: scenarioVus,
      duration: scenarioDuration,
      exec: 'providerRequestLoggingWritePath',
      tags: { flow: 'provider_log_write' },
      startTime: '2s',
    },
  },
  thresholds: {
    'http_req_failed{flow:auth_list}': ['rate<0.01'],
    'http_req_duration{flow:auth_list}': ['p(95)<400', 'p(99)<700'],
    'checks{flow:auth_list}': ['rate>0.99'],

    'http_req_failed{flow:rule_poll}': ['rate<0.01'],
    'http_req_duration{flow:rule_poll}': ['p(95)<900', 'p(99)<1200'],
    'checks{flow:rule_poll}': ['rate>0.99'],

    'http_req_failed{flow:provider_log_write}': ['rate<0.01'],
    'http_req_duration{flow:provider_log_write}': ['p(95)<700', 'p(99)<1000'],
    'checks{flow:provider_log_write}': ['rate>0.99'],
  },
};

function authHeaders() {
  if (!token) {
    fail('PERF_BEARER_TOKEN is required.');
  }
  return {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  };
}

function endpoint(path) {
  return `${baseUrl}${path.startsWith('/') ? path : `/${path}`}`;
}

export function authenticatedListEndpoints() {
  const headers = authHeaders();

  const rulesRes = http.get(endpoint(listPath), {
    headers,
    tags: { flow: 'auth_list', endpoint: 'watch_rules_list' },
  });

  const releasesRes = http.get(endpoint(releasesListPath), {
    headers,
    tags: { flow: 'auth_list', endpoint: 'watch_releases_list' },
  });

  check(rulesRes, {
    'watch-rules list is 200': (res) => res.status === 200,
  });
  check(releasesRes, {
    'watch-releases list is 200': (res) => res.status === 200,
  });

  sleep(0.25);
}

export function rulePollingTaskPath() {
  if (!ruleScenarioEnabled) {
    sleep(1);
    return;
  }

  if (!ruleId) {
    fail('PERF_RULE_ID is required when PERF_ENABLE_RULE_RUN=1.');
  }

  const headers = authHeaders();
  const path = ruleRunPathTemplate.replace('{rule_id}', ruleId);
  const res = http.post(endpoint(path), null, {
    headers,
    tags: { flow: 'rule_poll', endpoint: 'rule_run' },
  });

  check(res, {
    'rule run returns 200': (r) => r.status === 200,
  });

  sleep(0.5);
}

export function providerRequestLoggingWritePath() {
  const headers = authHeaders();

  const res = http.post(endpoint(searchPath), searchPayload, {
    headers,
    tags: { flow: 'provider_log_write', endpoint: 'search' },
  });

  check(res, {
    'search returns 200': (r) => r.status === 200,
  });

  sleep(0.25);
}
