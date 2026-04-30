#!/usr/bin/env bash
# Copy a source Postgres database to Render (or any target) using pg_dump/pg_restore.
#
# From repository root (temporary shell variables only; do not commit secrets):
#   export SOURCE_DATABASE_URL='postgresql://user:pass@localhost:5432/procore_int'
#   export RENDER_EXTERNAL_DATABASE_URL='postgres://user:pass@HOST:5432/db?sslmode=require'
#   bash backend/scripts/dump_restore_render_postgres.sh
#
# SOURCE may use postgresql+psycopg:// — normalized to postgresql:// for libpq.
# RENDER_EXTERNAL_DATABASE_URL: Render *External* Postgres URL from the dashboard.
# Falls back to TARGET_DATABASE_URL if RENDER_EXTERNAL_DATABASE_URL is unset.
#
# This script applies strict SSL *only* to pg_restore (Render). Local pg_dump typically
# hits Postgres without TLS; inheriting PGSSLMODE=require breaks that.
# For interactive psql to Render, use: backend/scripts/psql_render_external.sh

set -euo pipefail

normalize_url() {
  local url="$1"
  url="${url//postgresql+psycopg:\/\//postgresql:\/\/}"
  url="${url//postgres:\/\//postgresql:\/\/}"
  printf '%s' "$url"
}

# Downgrade verify-* in URI (libpq may honor URL over PGSSLMODE in some setups).
# Ensure sslmode=require is present for managed cloud targets.
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

if [[ "${SOURCE_DATABASE_URL:-}" == "" ]]; then
  echo "Set SOURCE_DATABASE_URL (e.g. local postgresql://... or postgresql+psycopg://...)" >&2
  exit 1
fi
RENDER_TARGET="${RENDER_EXTERNAL_DATABASE_URL:-${TARGET_DATABASE_URL:-}}"
if [[ "$RENDER_TARGET" == "" ]]; then
  echo "Set RENDER_EXTERNAL_DATABASE_URL (Render external URL, e.g. postgres://...?sslmode=require)" >&2
  exit 1
fi

SRC="$(normalize_url "$SOURCE_DATABASE_URL")"
DST="$(finalize_render_target_url "$(normalize_url "$RENDER_TARGET")")"

TMP="${TMPDIR:-/tmp}/procore_pg_dump_$$.dump"
trap 'rm -f "$TMP"' EXIT

echo "Dumping from source..."
(
  # Do not use PGSSLMODE=require here: typical localhost Postgres has no SSL.
  unset PGSSLMODE PGSSLROOTCERT PGSSLCERT PGSSLKEY PGSSLCRL 2>/dev/null || true
  pg_dump -Fc --no-owner -f "$TMP" "$SRC"
)

echo "Restoring to target..."
unset PGSSLROOTCERT PGSSLCERT PGSSLKEY PGSSLCRL 2>/dev/null || true
export PGSSLMODE=require
set +e
pg_restore --verbose --no-owner --no-acl -d "$DST" "$TMP"
rc=$?
set -e
# pg_restore exit 1 = warnings but often OK; 0 = clean
if [[ "$rc" -eq 1 ]]; then
  echo "pg_restore finished with exit 1 (warnings common). Review output above." >&2
  exit 0
fi
exit "$rc"
