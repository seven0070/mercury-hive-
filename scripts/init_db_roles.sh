#!/bin/sh
set -eu

echo "=== Creating Mercury Hive database roles ==="

psql \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=ON_ERROR_STOP=1 \
  --set=runtime_password="$POSTGRES_RUNTIME_PASSWORD" <<'SQL'

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Runtime role: minimal privileges, no admin capabilities
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'mercury_runtime') THEN
    CREATE ROLE mercury_runtime
      LOGIN PASSWORD :'runtime_password'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
END
$$;

GRANT CONNECT ON DATABASE mercury_hive TO mercury_runtime;
GRANT USAGE ON SCHEMA public TO mercury_runtime;

SQL

echo "Database roles created successfully."
