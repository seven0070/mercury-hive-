#!/bin/sh
set -eu
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=ON_ERROR_STOP=1 \
  --set=runtime_password="$POSTGRES_RUNTIME_PASSWORD" <<'SQL'
CREATE EXTENSION IF NOT EXISTS pgcrypto;
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mercury_test_runtime') THEN
    CREATE ROLE mercury_test_runtime LOGIN PASSWORD :'runtime_password'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
END $$;
GRANT CONNECT ON DATABASE mercury_hive_test TO mercury_test_runtime;
GRANT USAGE ON SCHEMA public TO mercury_test_runtime;
SQL
echo "Test roles created."
