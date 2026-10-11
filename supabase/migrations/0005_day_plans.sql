-- Day plans waiting for the user's OK (plan P6). Apply after 0004.
create table if not exists public.proposals (
  id text primary key,
  user_id text not null,
  date date not null,
  status text not null default 'pending'
    check (status in ('pending', 'accepted', 'partially_applied', 'rejected', 'superseded', 'expired')),
  items jsonb not null,
  chosen jsonb,  -- the items ticked on the card, applied by a spoken yes
  message_id text,
  expires_at timestamptz not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists proposals_user on public.proposals (user_id, date, status);
alter table public.proposals enable row level security;
drop policy if exists own_rows on public.proposals;
create policy own_rows on public.proposals for select to authenticated
  using (user_id = (select auth.uid())::text);
