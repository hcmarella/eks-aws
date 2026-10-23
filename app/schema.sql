CREATE TABLE IF NOT EXISTS ledger (case_id text, step text, result jsonb, created_at timestamptz DEFAULT now(), PRIMARY KEY (case_id, step));
CREATE TABLE IF NOT EXISTS step_events (id bigserial PRIMARY KEY, case_id text, step text, status text, at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS source_cases (case_id text PRIMARY KEY, data_version int, payload jsonb);
CREATE TABLE IF NOT EXISTS case_outbox (case_id text, data_version int, status text DEFAULT 'new', PRIMARY KEY (case_id, data_version));
CREATE TABLE IF NOT EXISTS cdc_watermark (source text PRIMARY KEY, last_commit_version bigint);
