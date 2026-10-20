-- The agent connects as this role. Even if a dangerous query slipped past the
-- SQL guard, the database itself refuses to write, and long queries are killed.
CREATE ROLE agent_ro LOGIN PASSWORD 'agent_ro'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;

REVOKE ALL ON SCHEMA public FROM agent_ro;
GRANT CONNECT ON DATABASE shop TO agent_ro;
GRANT USAGE ON SCHEMA shop TO agent_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA shop TO agent_ro;

ALTER ROLE agent_ro SET default_transaction_read_only = on;
ALTER ROLE agent_ro SET statement_timeout = '5s';
ALTER ROLE agent_ro SET search_path = shop;
