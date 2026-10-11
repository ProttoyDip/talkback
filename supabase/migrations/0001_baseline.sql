-- Baseline: the schema already live on 11 October 2026 (applied by hand
-- before migrations were tracked). Recorded so a fresh project can be
-- rebuilt; safe to run again.
--
-- Row Level Security is on with no policies: the publishable key can read
-- nothing. Only the server's secret key can (SECURITY.md T6).

create table if not exists public.memories (
  id text primary key,
  text text not null check (char_length(text) between 1 and 500),
  kind text not null check (kind in ('preference', 'fact', 'reminder')),
  source text not null check (source = 'user_utterance'),
  utterance text not null check (char_length(utterance) between 1 and 1000),
  created_at timestamptz not null default now(),
  confidence real not null check (confidence >= 0 and confidence <= 1),
  search tsvector generated always as (to_tsvector('english', text)) stored
);
create index if not exists memories_search on public.memories using gin (search);
alter table public.memories enable row level security;

create table if not exists public.app_settings (
  id integer primary key check (id = 1),
  data jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);
alter table public.app_settings enable row level security;
