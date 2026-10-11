-- Tasks, calendar blocks, reminders and your own skills (plan P5).
-- Apply after 0003, before deploying the code that uses it.
-- Times are timestamptz; rows are soft-deleted (deleted_at) for undo.

create table if not exists public.tasks (
  id text primary key,
  user_id text not null,
  title text not null check (char_length(title) between 1 and 200),
  notes text check (char_length(notes) <= 2000),
  status text not null default 'open' check (status in ('open', 'done', 'cancelled')),
  due_at timestamptz,
  priority text not null default 'normal' check (priority in ('low', 'normal', 'high')),
  completed_at timestamptz,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists tasks_user on public.tasks (user_id, status, due_at);

create table if not exists public.events (
  id text primary key,
  user_id text not null,
  title text not null check (char_length(title) between 1 and 200),
  starts_at timestamptz not null,
  ends_at timestamptz not null,
  kind text not null default 'block' check (kind in ('block', 'meeting', 'focus', 'personal')),
  status text not null default 'confirmed' check (status in ('confirmed', 'cancelled')),
  task_id text,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (ends_at > starts_at)
);
create index if not exists events_user on public.events (user_id, starts_at);

create table if not exists public.reminders (
  id text primary key,
  user_id text not null,
  text text not null check (char_length(text) between 1 and 300),
  due_at timestamptz not null,
  status text not null default 'scheduled'
    check (status in ('scheduled', 'delivered', 'acknowledged', 'cancelled', 'missed')),
  delivered_at timestamptz,
  delivered_via text,
  ack_at timestamptz,
  snooze_count integer not null default 0,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
-- The scheduler looks up due reminders across users (server only).
create index if not exists reminders_due on public.reminders (status, due_at);

create table if not exists public.user_skills (
  id text primary key,
  user_id text not null,
  name text not null check (char_length(name) between 1 and 60),
  triggers jsonb not null,
  allowed_tools jsonb not null,
  instructions text not null check (char_length(instructions) between 1 and 2000),
  summary text,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists user_skills_user on public.user_skills (user_id);

-- Row Level Security: a signed-in browser reaches only its own rows. The
-- server writes with its secret key and filters by user itself.
do $$
declare t text;
begin
  foreach t in array array['tasks', 'events', 'reminders', 'user_skills'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists own_rows on public.%I', t);
    execute format(
      'create policy own_rows on public.%I for select to authenticated using (user_id = (select auth.uid())::text)', t
    );
  end loop;
end $$;
