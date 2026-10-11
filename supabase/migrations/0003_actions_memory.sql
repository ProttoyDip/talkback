-- Action history with undo, and correction-aware memory (plan P4).
-- Apply after 0002_user_scoping.sql, before deploying the code that uses it.

-- Memories: status, where the words came from, what they are about (slot),
-- and which correction replaced them.
alter table public.memories
  add column if not exists status text not null default 'confirmed'
    check (status in ('confirmed', 'suggested', 'superseded', 'dismissed')),
  add column if not exists slot text,
  add column if not exists updated_at timestamptz,
  add column if not exists superseded_by text;

-- Only the user's own words (said, typed, edited) create a memory in use; a
-- suggestion from TalkBack waits for the user's OK (SECURITY.md T3).
alter table public.memories drop constraint if exists memories_source_check;
alter table public.memories add constraint memories_source_check
  check (source in ('user_utterance', 'user_text', 'user_edit', 'assistant_suggestion'));

create index if not exists memories_slot on public.memories (user_id, slot);

create table if not exists public.actions (
  id text primary key,
  user_id text not null,
  session_id text,
  call_id text,
  tool text not null,
  status text not null check (status in ('done', 'failed', 'cancelled', 'declined', 'expired', 'undone')),
  summary text not null check (char_length(summary) <= 300),
  target_kind text,
  target_id text,
  undo jsonb,
  idempotency_key text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  finished_at timestamptz,
  undone_at timestamptz,
  unique (user_id, idempotency_key)
);
create index if not exists actions_user on public.actions (user_id, created_at desc);
alter table public.actions enable row level security;

-- Read-only for signed-in users: only the server writes history, so a
-- browser cannot plant an action with a forged undo.
drop policy if exists own_rows on public.actions;
create policy own_rows on public.actions for select to authenticated
  using (user_id = (select auth.uid())::text);
