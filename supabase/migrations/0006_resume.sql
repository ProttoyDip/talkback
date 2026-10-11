-- Resume an unfinished conversation (plan P7). Apply after 0005.
-- Facts only: the user's goal (their words), what was done, what was open.
-- recent_turns stays null unless the user turns on "keep the last 6 turns".
create table if not exists public.conversation_states (
  id text primary key,
  user_id text not null,
  session_id text not null,
  goal text not null check (char_length(goal) <= 200),
  decisions jsonb,
  pending jsonb,
  recent_turns jsonb,
  status text not null default 'open' check (status in ('open', 'resumed', 'dismissed')),
  closed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists conversation_states_user on public.conversation_states (user_id, status, updated_at desc);
alter table public.conversation_states enable row level security;
drop policy if exists own_rows on public.conversation_states;
create policy own_rows on public.conversation_states for select to authenticated
  using (user_id = (select auth.uid())::text);
