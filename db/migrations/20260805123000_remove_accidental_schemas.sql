-- migrate:up

-- These empty schemas were accidentally created while generating schema.sql.
DROP SCHEMA IF EXISTS schema;
DROP SCHEMA IF EXISTS "schema.sql";

-- migrate:down

CREATE SCHEMA IF NOT EXISTS schema;
CREATE SCHEMA IF NOT EXISTS "schema.sql";
