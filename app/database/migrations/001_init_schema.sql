-- ForgeAI core schema (Supabase / PostgreSQL 15+)
-- UUID keys, FKs, timestamps, JSONB artifacts, indexes, RLS on user-owned data.
create extension if not exists pgcrypto;

-- ------------------------------------------------------------------ profiles
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  role text not null default 'engineer' check (role in ('engineer','reviewer','admin')),
  created_at timestamptz not null default now()
);

-- ------------------------------------------------------------------ projects
create table if not exists public.projects (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  brief text not null,
  status text not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists projects_owner_idx on public.projects(owner_id);

-- ------------------------------------------------------------------ documents
create table if not exists public.documents (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete cascade,
  filename text not null,
  file_type text not null,
  size_bytes bigint not null,
  current_hash text not null,
  current_version int not null default 1,
  storage_path text,
  status text not null default 'ingested' check (status in ('ingested','failed','removed')),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (project_id, filename)
);
create index if not exists documents_project_idx on public.documents(project_id);

create table if not exists public.document_versions (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
  version int not null,
  content_hash text not null,
  chunk_count int not null default 0,
  change_type text not null default 'added' check (change_type in ('added','modified','removed','unchanged')),
  storage_path text,
  created_at timestamptz not null default now(),
  unique (document_id, version)
);
create index if not exists document_versions_doc_idx on public.document_versions(document_id);

-- ------------------------------------------------------------------ runs
create table if not exists public.factory_runs (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete cascade,
  status text not null default 'created',
  stages jsonb not null default '{}'::jsonb,
  stage_messages jsonb not null default '{}'::jsonb,
  budget jsonb not null default '{}'::jsonb,
  usage jsonb not null default '{}'::jsonb,
  stop_reason text,
  final_agent_version int,
  created_by uuid references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists factory_runs_project_idx on public.factory_runs(project_id);

create table if not exists public.interview_records (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.factory_runs(id) on delete cascade,
  analysis jsonb not null,
  questions jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists interview_records_run_idx on public.interview_records(run_id);

-- ------------------------------------------------------------------ requirements & approval
create table if not exists public.requirements (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.factory_runs(id) on delete cascade,
  version int not null,
  kind text not null check (kind in ('original','edited','approved','rejected')),
  content jsonb not null,
  groundability jsonb,
  created_by uuid references auth.users(id),
  created_at timestamptz not null default now(),
  unique (run_id, version)
);
create index if not exists requirements_run_idx on public.requirements(run_id);

create table if not exists public.approval_records (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.factory_runs(id) on delete cascade,
  requirements_id uuid references public.requirements(id) on delete set null,
  decision text not null check (decision in ('approved','rejected')),
  approver_id uuid references auth.users(id),
  approver_label text not null,
  comment text,
  diff jsonb not null default '[]'::jsonb,
  decided_at timestamptz not null default now()
);
create index if not exists approval_records_run_idx on public.approval_records(run_id);

-- ------------------------------------------------------------------ agents
create table if not exists public.agent_definitions (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete cascade,
  run_id uuid references public.factory_runs(id) on delete set null,
  agent_name text not null,
  latest_version int not null default 1,
  final_version int,
  origin text not null default 'forgeai' check (origin in ('forgeai','human_baseline')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists agent_definitions_project_idx on public.agent_definitions(project_id);

create table if not exists public.agent_versions (
  id uuid primary key default gen_random_uuid(),
  agent_definition_id uuid not null references public.agent_definitions(id) on delete cascade,
  version int not null,
  parent_version int,
  definition jsonb not null,
  change_summary jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  unique (agent_definition_id, version)
);
create index if not exists agent_versions_def_idx on public.agent_versions(agent_definition_id);

create table if not exists public.tool_registry (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  description text not null,
  input_schema jsonb not null,
  output_schema jsonb not null,
  permission text not null default 'read_only',
  requires_network boolean not null default false,
  enabled boolean not null default true,
  created_at timestamptz not null default now()
);

-- ------------------------------------------------------------------ evaluation
create table if not exists public.evaluation_datasets (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.factory_runs(id) on delete cascade,
  version int not null default 1,
  case_count int not null,
  generation_config jsonb not null default '{}'::jsonb,
  rejected_candidates jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  unique (run_id, version)
);
create index if not exists evaluation_datasets_run_idx on public.evaluation_datasets(run_id);

create table if not exists public.evaluation_cases (
  id uuid primary key default gen_random_uuid(),
  dataset_id uuid not null references public.evaluation_datasets(id) on delete cascade,
  test_id text not null,
  category text not null check (category in ('answerable','out_of_scope','edge_case')),
  subtype text,
  question text not null,
  expected_behavior text not null,
  expected_sources jsonb not null default '[]'::jsonb,
  expected_facts jsonb not null default '[]'::jsonb,
  must_refuse boolean not null default false,
  difficulty text not null check (difficulty in ('easy','medium','hard')),
  evaluation_rationale text,
  evidence jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (dataset_id, test_id)
);
create index if not exists evaluation_cases_dataset_idx on public.evaluation_cases(dataset_id);

create table if not exists public.evaluation_results (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.factory_runs(id) on delete cascade,
  agent_version_id uuid references public.agent_versions(id) on delete set null,
  agent_version int not null,
  case_id uuid references public.evaluation_cases(id) on delete set null,
  test_id text not null,
  iteration int not null,
  label text not null default 'factory',
  passed boolean not null,
  metrics jsonb not null,
  answer jsonb not null,
  evidence jsonb not null default '[]'::jsonb,
  deterministic_checks jsonb not null default '{}'::jsonb,
  judge jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists evaluation_results_run_iter_idx on public.evaluation_results(run_id, iteration);
create index if not exists evaluation_results_case_idx on public.evaluation_results(case_id);

create table if not exists public.failure_records (
  id uuid primary key default gen_random_uuid(),
  result_id uuid not null references public.evaluation_results(id) on delete cascade,
  run_id uuid not null references public.factory_runs(id) on delete cascade,
  category text not null check (category in ('retrieval_miss','prompt_defect','hallucination',
                                             'wrong_refusal','tool_defect','output_contract_defect')),
  explanation text,
  created_at timestamptz not null default now()
);
create index if not exists failure_records_run_idx on public.failure_records(run_id);

create table if not exists public.scorecards (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.factory_runs(id) on delete cascade,
  iteration int not null,
  agent_version int not null,
  label text not null default 'factory',
  content jsonb not null,
  created_at timestamptz not null default now()
);
create index if not exists scorecards_run_idx on public.scorecards(run_id, iteration);

create table if not exists public.optimization_iterations (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.factory_runs(id) on delete cascade,
  iteration int not null,
  from_version int not null,
  to_version int,
  score_before numeric not null,
  score_after numeric,
  record jsonb not null,
  decision text not null check (decision in ('continue','stop')),
  created_at timestamptz not null default now(),
  unique (run_id, iteration)
);
create index if not exists optimization_iterations_run_idx on public.optimization_iterations(run_id, iteration);

create table if not exists public.change_logs (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.factory_runs(id) on delete cascade,
  iteration int not null,
  agent_version int not null,
  field_path text not null,
  old_value jsonb,
  new_value jsonb,
  reason text not null,
  created_at timestamptz not null default now()
);
create index if not exists change_logs_run_idx on public.change_logs(run_id, iteration);

-- ------------------------------------------------------------------ regression / baseline
create table if not exists public.regression_runs (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete cascade,
  base_run_id uuid not null references public.factory_runs(id) on delete cascade,
  document_changes jsonb not null,
  summary jsonb not null,
  report jsonb not null,
  created_at timestamptz not null default now()
);
create index if not exists regression_runs_project_idx on public.regression_runs(project_id);

create table if not exists public.baseline_comparisons (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.factory_runs(id) on delete cascade,
  factory_agent_version int not null,
  baseline_name text not null,
  results jsonb not null,
  created_at timestamptz not null default now()
);
create index if not exists baseline_comparisons_run_idx on public.baseline_comparisons(run_id);

-- ------------------------------------------------------------------ artifacts & audit
create table if not exists public.artifacts (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references public.factory_runs(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  kind text not null,
  filename text not null,
  storage_path text not null,
  sha256 text not null,
  size_bytes bigint not null,
  created_at timestamptz not null default now()
);
create index if not exists artifacts_run_idx on public.artifacts(run_id);

create table if not exists public.audit_logs (
  id uuid primary key default gen_random_uuid(),
  actor_id uuid references auth.users(id),
  actor_label text,
  project_id uuid references public.projects(id) on delete cascade,
  run_id uuid references public.factory_runs(id) on delete cascade,
  action text not null,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists audit_logs_run_idx on public.audit_logs(run_id);
create index if not exists audit_logs_project_idx on public.audit_logs(project_id);

-- ------------------------------------------------------------------ approval gate in the DB
-- An agent version can only be inserted for a run that has an 'approved' record.
create or replace function public.enforce_approval_before_agent() returns trigger
language plpgsql as $$
declare v_run uuid;
begin
  select run_id into v_run from public.agent_definitions where id = new.agent_definition_id;
  if v_run is not null and not exists (
      select 1 from public.approval_records a where a.run_id = v_run and a.decision = 'approved') then
    raise exception 'agent generation blocked: requirements for run % are not approved', v_run;
  end if;
  return new;
end $$;
drop trigger if exists agent_versions_require_approval on public.agent_versions;
create trigger agent_versions_require_approval before insert on public.agent_versions
  for each row execute function public.enforce_approval_before_agent();

-- evaluation results are append-only (never replaced)
create or replace function public.forbid_update() returns trigger language plpgsql as $$
begin raise exception '% is append-only', tg_table_name; end $$;
drop trigger if exists evaluation_results_append_only on public.evaluation_results;
create trigger evaluation_results_append_only before update on public.evaluation_results
  for each row execute function public.forbid_update();
drop trigger if exists approval_records_append_only on public.approval_records;
create trigger approval_records_append_only before update on public.approval_records
  for each row execute function public.forbid_update();
