-- Documents and research projects (plan P8). Apply after 0006.
-- Passages carry NVIDIA embeddings (nvidia/nemotron-3-embed-1b, 2048
-- dimensions). Search is exact cosine over one user's passages (at most
-- about 4,000): HNSW indexes stop at 2,000 dimensions, and filtering by user
-- first is what keeps it fast. Document and note text is untrusted data.
create extension if not exists vector with schema extensions;

create table if not exists public.documents (
  id text primary key,
  user_id text not null,
  title text not null check (char_length(title) <= 200),
  filename text not null check (char_length(filename) <= 200),
  kind text not null check (kind in ('pdf', 'txt', 'md')),
  size_bytes integer not null check (size_bytes <= 5242880),
  pages integer check (pages <= 50),
  chunks integer not null default 0,
  status text not null default 'processing' check (status in ('processing', 'ready', 'failed')),
  error text check (char_length(error) <= 200),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists documents_user on public.documents (user_id, created_at);

create table if not exists public.projects (
  id text primary key,
  user_id text not null,
  name text not null check (char_length(name) <= 100),
  description text check (char_length(description) <= 300),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists projects_user on public.projects (user_id, name);

create table if not exists public.project_notes (
  id text primary key,
  user_id text not null,
  project_id text not null references public.projects (id) on delete cascade,
  text text not null check (char_length(text) <= 2000),
  sources jsonb,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists project_notes_project on public.project_notes (user_id, project_id, created_at);

create table if not exists public.knowledge_chunks (
  id text primary key,
  user_id text not null,
  kind text not null check (kind in ('document', 'project_note')),
  source_id text not null,
  note_id text,
  ord integer not null,
  locator text,
  text text not null check (char_length(text) <= 1200),
  embedding extensions.vector(2048),
  tsv tsvector generated always as (to_tsvector('simple', text)) stored,
  created_at timestamptz default now()
);
create index if not exists knowledge_chunks_user on public.knowledge_chunks (user_id, kind, source_id);
create index if not exists knowledge_chunks_tsv on public.knowledge_chunks using gin (tsv);

alter table public.documents enable row level security;
alter table public.projects enable row level security;
alter table public.project_notes enable row level security;
alter table public.knowledge_chunks enable row level security;
drop policy if exists own_rows on public.documents;
create policy own_rows on public.documents for select to authenticated using (user_id = (select auth.uid())::text);
drop policy if exists own_rows on public.projects;
create policy own_rows on public.projects for select to authenticated using (user_id = (select auth.uid())::text);
drop policy if exists own_rows on public.project_notes;
create policy own_rows on public.project_notes for select to authenticated using (user_id = (select auth.uid())::text);
drop policy if exists own_rows on public.knowledge_chunks;
create policy own_rows on public.knowledge_chunks for select to authenticated using (user_id = (select auth.uid())::text);

-- One user's best passages: 0.75 cosine similarity + 0.25 keyword rank.
-- Without a query embedding (NVIDIA unreachable) keywords alone decide.
-- Only the server (service role) may call it: it takes the user id.
create or replace function public.match_chunks(
  p_user_id text, p_kind text, p_query extensions.vector(2048), p_text text, p_count integer
) returns table (id text, source_id text, note_id text, ord integer, locator text, text text, score double precision)
language sql stable security invoker set search_path = public, extensions
as $$
  select c.id, c.source_id, c.note_id, c.ord, c.locator, c.text,
    0.75 * (case when p_query is null or c.embedding is null then 0 else 1 - (c.embedding <=> p_query) end)
      + 0.25 * least(ts_rank(c.tsv, websearch_to_tsquery('simple', p_text)), 1) as score
  from public.knowledge_chunks c
  where c.user_id = p_user_id and c.kind = p_kind
    -- The same cut-off as the local search: unrelated passages score under 0.15.
    and ((p_query is not null and c.embedding is not null and 1 - (c.embedding <=> p_query) >= 0.2)
      or c.tsv @@ websearch_to_tsquery('simple', p_text))
  order by score desc
  limit least(greatest(p_count, 1), 10);
$$;
revoke execute on function public.match_chunks(text, text, extensions.vector, text, integer) from public, anon, authenticated;
