#!/bin/sh
set -eu

echo "=== Creating Mercury Hive database roles ==="

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=ON_ERROR_STOP=1 <<EOF
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'mercury_runtime') THEN
    EXECUTE format('CREATE ROLE mercury_runtime LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS', '$POSTGRES_RUNTIME_PASSWORD');
  END IF;
END
\$\$;

GRANT CONNECT ON DATABASE "$POSTGRES_DB" TO mercury_runtime;
GRANT USAGE ON SCHEMA public TO mercury_runtime;
EOF

echo "Database roles created successfully."
