#!/usr/bin/env bash
# Deploy the already-pushed current Git commit to the Shrimp Tank Render services.
#
# One-time setup:
#   1. Create the Render API Web Service and frontend Static Site as described in README.md.
#   2. Copy each service's deploy hook from Render > Settings.
#   3. Copy scripts/deploy-render.env.example to .deploy.env and add the two hook URLs.
#   4. Log into SpacetimeDB locally; the script publishes the state module before
#      triggering the API deploy.
#
# The deploy-hook URLs are secrets. Do not commit .deploy.env.

set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
config_file="${DEPLOY_CONFIG:-$project_root/.deploy.env}"
dry_run=false
skip_checks=false
target="all"

usage() {
  cat <<'USAGE'
Usage: ./scripts/deploy-render.sh [options]

Options:
  --api              Deploy only the FastAPI service.
  --frontend         Deploy only the Vite static site.
  --skip-checks      Skip Python syntax and frontend production-build checks.
  --dry-run          Print the actions without triggering Render.
  --config PATH      Read deploy-hook settings from PATH.
  -h, --help         Show this help.
USAGE
}

fail() {
  printf 'deploy-render: %s\n' "$*" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    --api)
      target="api"
      ;;
    --frontend)
      target="frontend"
      ;;
    --skip-checks)
      skip_checks=true
      ;;
    --dry-run)
      dry_run=true
      ;;
    --config)
      (($# >= 2)) || fail "--config needs a file path."
      config_file="$2"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown option: $1"
      ;;
  esac
  shift
done

cd "$project_root"

for command in git curl python3 npm; do
  command -v "$command" >/dev/null 2>&1 || fail "Missing required command: $command"
done

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail "This script must run from a Git working tree."

if [[ -f "$config_file" ]]; then
  # shellcheck disable=SC1090
  source "$config_file"
fi

publish_spacetime() {
  local database_name="${SPACETIMEDB_DATABASE:-credit-tank-state}"
  local server_name="${SPACETIMEDB_SERVER:-maincloud}"
  command -v spacetime >/dev/null 2>&1 || fail "Missing required command: spacetime"

  if [[ "$dry_run" == true ]]; then
    printf 'Would publish SpacetimeDB module to %s on %s.\n' "$database_name" "$server_name"
    return
  fi

  printf 'Publishing SpacetimeDB module to %s…\n' "$database_name"
  spacetime publish "$database_name" \
    --module-path "$project_root/spacetime/spacetimedb" \
    --server "$server_name" \
    --no-config \
    --yes
}

if [[ -n "$(git status --porcelain)" ]]; then
  fail "Working tree has uncommitted changes. Commit and push the deployment first."
fi

git rev-parse --verify "@{u}" >/dev/null 2>&1 || fail "Current branch has no upstream. Push it and set an upstream first."
commit_sha="$(git rev-parse HEAD)"
upstream_sha="$(git rev-parse "@{u}")"
[[ "$commit_sha" == "$upstream_sha" ]] || fail "Current commit differs from its upstream branch. Push or pull before deploying."

if [[ "$skip_checks" == false ]]; then
  printf 'Checking backend syntax…\n'
  python3 -m compileall -q backend/app
  printf 'Building frontend…\n'
  (
    cd frontend
    npm ci
    npm run build
  )
fi

trigger() {
  local service_name="$1"
  local hook_url="$2"
  [[ -n "$hook_url" ]] || fail "Missing deploy hook for $service_name. Set it in $config_file."

  if [[ "$dry_run" == true ]]; then
    printf 'Would trigger %s deploy for commit %s.\n' "$service_name" "$commit_sha"
    return
  fi

  printf 'Triggering %s deploy for %s…\n' "$service_name" "$commit_sha"
  curl --fail --silent --show-error --location --request POST "$hook_url" >/dev/null
  printf '%s deploy accepted by Render.\n' "$service_name"
}

if [[ "$target" == "all" || "$target" == "api" ]]; then
  publish_spacetime
  trigger "API" "${RENDER_API_DEPLOY_HOOK:-}"
fi

if [[ "$target" == "all" || "$target" == "frontend" ]]; then
  trigger "frontend" "${RENDER_FRONTEND_DEPLOY_HOOK:-}"
fi

if [[ "$dry_run" == true ]]; then
  printf 'Dry run complete. No Render deploy was triggered.\n'
else
  printf 'Deployment requests sent. Follow progress in the Render dashboard.\n'
fi
