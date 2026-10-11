-- Accounts: every row belongs to one user (plan P2, SECURITY.md T6).
--
-- user_id is text, not a foreign key to auth.users, because the server
-- without accounts (AUTH_MODE=off) stores everything as user "local".
-- The server's secret key bypasses Row Level Security, so the server filters
-- by user itself (backend/app/db); the policies below protect against any
-- direct browser access with a signed-in user's token.

alter table public.memories add column if not exists user_id text not null default 'local';
create index if not exists memories_user on public.memories (user_id, created_at);

create table if not exists public.user_settings (
  id text primary key,                 -- the same as user_id: one row per user
  user_id text not null unique,
  data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (id = user_id)
);
alter table public.user_settings enable row level security;

-- The shared settings used before accounts become the local user's.
insert into public.user_settings (id, user_id, data)
select 'local', 'local', data from public.app_settings where id = 1
on conflict (id) do nothing;

drop policy if exists own_rows on public.memories;
create policy own_rows on public.memories for all to authenticated
  using (user_id = (select auth.uid())::text)
  with check (user_id = (select auth.uid())::text);

drop policy if exists own_rows on public.user_settings;
create policy own_rows on public.user_settings for all to authenticated
  using (user_id = (select auth.uid())::text)
  with check (user_id = (select auth.uid())::text);
