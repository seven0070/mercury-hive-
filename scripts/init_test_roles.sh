#!/bin/sh
set -eu

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=ON_ERROR_STOP=1 <<EOF
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'mercury_test_runtime') THEN
    EXECUTE format('CREATE ROLE mercury_test_runtime LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS', '$POSTGRES_RUNTIME_PASSWORD');
  END IF;
END
\$\$;

GRANT CONNECT ON DATABASE "$POSTGRES_DB" TO mercury_test_runtime;
GRANT USAGE ON SCHEMA public TO mercury_test_runtime;
EOF

echo "Test roles created."
