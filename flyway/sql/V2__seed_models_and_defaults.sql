-- V2__seed_models_and_defaults.sql
-- Optional seeds: model registry and a demo DOC task (without id; your app usually assigns it).

CREATE TABLE IF NOT EXISTS models (
  name      text PRIMARY KEY,
  provider  text,
  family    text,
  enabled   boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO models(name, provider, family, enabled)
VALUES
  ('qwen2.5:7b', 'ollama', 'qwen', true),
  ('llama3.1:8b', 'ollama', 'llama', true)
ON CONFLICT (name) DO NOTHING;

