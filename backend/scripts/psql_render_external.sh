#!/usr/bin/env bash
# Open psql to Render using RENDER_EXTERNAL_DATABASE_URL with the same SSL mitigations
# as dump_restore_render_postgres.sh (local PGSSL* / verify-full often breaks Render).
#
#   export RENDER_EXTERNAL_DATABASE_URL='postgres://...'
#   bash backend/scripts/psql_render_external.sh
#   bash backend/scripts/psql_render_external.sh -c '\dt'

set -euo pipefail

unset PGSSLROOTCERT PGSSLCERT PGSSLKEY PGSSLCRL 2>/dev/null || true
export PGSSLMODE=require

if [[ "${RENDER_EXTERNAL_DATABASE_URL:-}" == "" ]]; then
  echo "Set RENDER_EXTERNAL_DATABASE_URL" >&2
  exit 1
fi

normalize_url() {
  local url="$1"
  url="${url//postgresql+psycopg:\/\//postgresql:\/\/}"
  url="${url//postgres:\/\//postgresql:\/\/}"
  printf '%s' "$url"
}
finalize_render_target_url() {
  local url="$1"
  url="${url//sslmode=verify-full/sslmode=require}"
  url="${url//sslmode=verify-ca/sslmode=require}"
  if [[ "$url" != *"sslmode="* ]]; then
    if [[ "$url" == *"?"* ]]; then
      url="${url}&sslmode=require"
    else
      url="${url}?sslmode=require"
    fi
  fi
  printf '%s' "$url"
}

DST="$(finalize_render_target_url "$(normalize_url "$RENDER_EXTERNAL_DATABASE_URL")")"
exec psql "$DST" "$@"
