#!/usr/bin/env bash
set -euo pipefail

worker_pid=""
cleanup() {
  if [[ -n "${worker_pid}" ]]; then
    kill "${worker_pid}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

celery -A app.core.celery_app.celery_app worker \
  --loglevel=WARNING \
  --pool=solo \
  --concurrency=1 \
  --queues=waxwatch \
  >/tmp/celery-worker.log 2>&1 &
worker_pid=$!

ready_pattern='celery@|\.> waxwatch\s+exchange=waxwatch\(direct\) key=waxwatch'
for _ in $(seq 1 30); do
  if ! kill -0 "$worker_pid" 2>/dev/null; then
    echo "Celery worker exited before readiness"
    tail -n 200 /tmp/celery-worker.log || true
    exit 1
  fi

  if grep -Eq "$ready_pattern" /tmp/celery-worker.log; then
    break
  fi

  sleep 1
done

if ! grep -Eq "$ready_pattern" /tmp/celery-worker.log; then
  echo "Celery worker did not become ready"
  tail -n 200 /tmp/celery-worker.log || true
  exit 1
fi

pytest -q tests/test_celery_redis_integration.py -rA --no-cov
