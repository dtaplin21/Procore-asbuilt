#!/usr/bin/env bash
# Copy a source Postgres database to Render (or any target) using pg_dump/pg_restore.
#
# From repository root:
#   export SOURCE_DATABASE_URL='postgresql://user:pass@localhost:5432/procore_int'
#   export TARGET_DATABASE_URL='postgresql://user:pass@HOST:5432/db?sslmode=require'
#   bash backend/scripts/dump_restore_render_postgres.sh
#
# SOURCE may use postgresql+psycopg:// — normalized to postgresql:// for libpq.
# TARGET: use Render's *external* URL when running from your laptop.

set -euo pipefail

normalize_url() {
  local url="$1"
  url="${url//postgresql+psycopg:\/\//postgresql:\/\/}"
  url="${url//postgres:\/\//postgresql:\/\/}"
  printf '%s' "$url"
}

if [[ "${SOURCE_DATABASE_URL:-}" == "" ]]; then
  echo "Set SOURCE_DATABASE_URL (e.g. local postgresql://... or postgresql+psycopg://...)" >&2
  exit 1
fi
if [[ "${TARGET_DATABASE_URL:-}" == "" ]]; then
  echo "Set TARGET_DATABASE_URL (e.g. Render external postgresql://...?sslmode=require)" >&2
  exit 1
fi

SRC="$(normalize_url "$SOURCE_DATABASE_URL")"
DST="$(normalize_url "$TARGET_DATABASE_URL")"

TMP="${TMPDIR:-/tmp}/procore_pg_dump_$$.dump"
trap 'rm -f "$TMP"' EXIT

echo "Dumping from source..."
pg_dump -Fc --no-owner -f "$TMP" "$SRC"

echo "Restoring to target..."
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
