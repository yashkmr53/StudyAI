#!/usr/bin/env bash
#
# Canonical StudyAI backend test command.
#
# Runs the Django suite inside the Docker api container against PostgreSQL/pgvector,
# using the deterministic test settings module (config.settings.ci):
#   - throttling disabled by default (explicit throttle tests opt back in),
#   - Celery eager (jobs execute in-process, never on the live broker),
#   - DummyCache (no shared rate-limit state between tests).
#
# Developers do NOT set DJANGO_SETTINGS_MODULE by hand — this script pins it.
#
# Usage:
#   ./scripts/test.sh                                    # full suite (label: tests)
#   ./scripts/test.sh tests.api.test_hardening.RateLimitTests
#   ./scripts/test.sh tests.unit tests.integration       # multiple labels
#
# Requires: Docker Desktop running, .env present at repo root, stack started via
# `docker compose up -d --build` (first time). Never deletes volumes or data.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

die() {
    printf '\nERROR: %s\n\n' "$*" >&2
    exit 1
}

step() { printf '==> %s\n' "$*"; }

command -v docker >/dev/null 2>&1 ||
    die "docker CLI not found. Start Docker Desktop, then re-run ./scripts/test.sh"

[ -f .env ] ||
    die ".env missing at repo root. Create it first:
         cp .env.example .env      # then fill in YOUR OWN generated values
         See docs/docker-development-environment.md."

step "Checking stack (api, db)"
docker compose exec -T api python -c "pass" 2>/dev/null ||
    die "api container is not running. Start the stack, then re-run ./scripts/test.sh:
         docker compose up -d --build"
docker compose exec -T db pg_isready -q >/dev/null 2>&1 ||
    die "db container is not accepting connections yet. Inspect it with:
         docker compose logs db
         docker compose restart db"

step "Verifying image matches working tree"
stale=$(docker compose run --rm --no-deps -T -v "$PWD/backend:/src:ro" api python - <<'PY'
import hashlib, pathlib, sys

def tree_hash(root):
    digest = hashlib.sha256()
    skip = {"__pycache__", ".pytest_cache", "var"}
    for path in sorted(pathlib.Path(root).rglob("*.py")):
        if skip & set(path.parts):
            continue
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()

image_tree = tree_hash("/app")
source_tree = tree_hash("/src")
print("STALE" if image_tree != source_tree else "ok")
PY
) || die "Could not compare image contents with the working tree."
[ "$stale" = "ok" ] ||
    die "backend code inside the api image differs from your working tree.
         Rebuild so tests exercise the code you edited:
             docker compose build api worker && docker compose up -d api worker"

labels=("$@")
[ "${#labels[@]}" -eq 0 ] && labels=("tests")

step "Running tests (settings: config.settings.ci, database: PostgreSQL/pgvector)"
exec docker compose exec -T \
    -e DJANGO_SETTINGS_MODULE=config.settings.ci \
    api python manage.py test "${labels[@]}" --noinput -v 2
