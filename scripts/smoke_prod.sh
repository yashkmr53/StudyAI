#!/usr/bin/env bash
#
# Production-configuration smoke check (NOT the test suite).
#
# Validates that the running Docker stack still behaves like production:
#   - Django boots under config.settings.prod (manage.py check)
#   - production rate limiting remains ENABLED (auth 30/min via LocMemCache)
#   - production Celery remains NON-eager
#   - liveness (/healthz) and readiness (/readyz incl. DB roundtrip) respond 200
#   - authentication routing is live and the real auth throttle engages
#     (no-write password-reset probes: early 202s, then HTTP 429).
#     gunicorn runs 3 workers and LocMemCache counters are per-process, so the
#     probe loops until SOME worker's 30/min bucket fills (cap 120 requests).
#   - Celery worker responds through the real Redis broker (inspect ping)
#
# Read-only with respect to application data; never prints secret values.
# Note: the throttle probe briefly (<= 60 s) fills the auth rate bucket for
# requests originating from the api container itself (127.0.0.1).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

die() {
    printf '\nSMOKE FAILED: %s\n\n' "$*" >&2
    exit 1
}

step() { printf '==> %s\n' "$*"; }

command -v docker >/dev/null 2>&1 ||
    die "docker CLI not found. Start Docker Desktop and re-run."

for svc in api db redis worker; do
    docker compose ps --services --status running 2>/dev/null | grep -qx "$svc" ||
        die "service '$svc' is not running. Start it: docker compose up -d --build"
done

step "Django boots under prod settings"
docker compose exec -T api python manage.py check >/dev/null ||
    die "manage.py check failed under config.settings.prod"

step "Production security/throttle/Celery configuration"
prod_flags=$(docker compose exec -T api python - <<'PY'
from django.conf import settings

checks = {
    "rate_limiting_enabled": settings.RATE_LIMITING_ENABLED is True,
    "celery_not_eager": settings.CELERY_TASK_ALWAYS_EAGER is False,
    "auth_rate_30_per_min":
        settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["auth"] == "30/min",
    "cache_is_locremem":
        settings.CACHES["default"]["BACKEND"].endswith("locmem.LocMemCache"),
}
for name, ok in checks.items():
    print(f"{name}={'PASS' if ok else 'FAIL'}")
PY
) || die "could not introspect production settings"
printf '%s\n' "$prod_flags" | grep FAIL >/dev/null &&
    { printf '%s\n' "$prod_flags"; die "production configuration has been weakened"; }
printf '%s\n' "$prod_flags" | sed 's/^/    /'

step "Liveness /healthz"
health=$(docker compose exec -T api python -c \
    "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/healthz', timeout=5).status)") ||
    die "/healthz did not answer"
[ "$health" = "200" ] || die "/healthz returned $health"

step "Readiness /readyz (database roundtrip)"
ready=$(docker compose exec -T api python - <<'PY'
import json, urllib.request

with urllib.request.urlopen("http://localhost:8000/readyz", timeout=5) as response:
    print(response.status, json.load(response)["database"])
PY
) || die "/readyz did not answer"
[ "$ready" = "200 True" ] || die "/readyz not healthy: $ready"

step "Auth live + production throttle engages (no-write password-reset probes)"
auth_probe=$(docker compose exec -T api python - <<'PY'
import urllib.error, urllib.request

statuses = []
for _ in range(120):
    request = urllib.request.Request(
        "http://localhost:8000/api/v1/auth/password-reset",
        data=b'{"email":"smoke-probe@example.com"}',
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        status = urllib.request.urlopen(request, timeout=5).status
    except urllib.error.HTTPError as error:
        status = error.code
    statuses.append(status)
    if status == 429:
        break
print("PASS" if statuses[0] == 202 and 429 in statuses else f"FAIL {statuses}")
PY
) || die "throttle probe could not run"
[ "$auth_probe" = "PASS" ] ||
    die "password-reset did not behave like production (expected early 202s then 429): $auth_probe"

step "Celery worker reachable via Redis broker"
ping=$(docker compose exec -T worker celery -A config inspect ping --timeout 10 2>&1 || true)
echo "$ping" | sed 's/^/    /'
echo "$ping" | grep -q pong ||
    die "celery worker did not answer inspect ping"

printf '\nPRODUCTION SMOKE: ALL CHECKS PASSED\n'
