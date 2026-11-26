-- Row Level Security: users only see rows belonging to projects they own.
create or replace function public.owns_project(p uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.projects where id = p and owner_id = auth.uid());
$$;

create or replace function public.owns_run(r uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.factory_runs fr join public.projects p on p.id = fr.project_id
                 where fr.id = r and p.owner_id = auth.uid());
$$;

alter table public.profiles enable row level security;
alter table public.projects enable row level security;
alter table public.documents enable row level security;
alter table public.document_versions enable row level security;
alter table public.factory_runs enable row level security;
alter table public.interview_records enable row level security;
alter table public.requirements enable row level security;
alter table public.approval_records enable row level security;
alter table public.agent_definitions enable row level security;
alter table public.agent_versions enable row level security;
alter table public.tool_registry enable row level security;
alter table public.evaluation_datasets enable row level security;
alter table public.evaluation_cases enable row level security;
alter table public.evaluation_results enable row level security;
alter table public.failure_records enable row level security;
alter table public.scorecards enable row level security;
alter table public.optimization_iterations enable row level security;
alter table public.change_logs enable row level security;
alter table public.regression_runs enable row level security;
alter table public.baseline_comparisons enable row level security;
alter table public.artifacts enable row level security;
alter table public.audit_logs enable row level security;

drop policy if exists profiles_self on public.profiles;
create policy profiles_self on public.profiles for all using (id = auth.uid()) with check (id = auth.uid());

drop policy if exists projects_owner on public.projects;
create policy projects_owner on public.projects for all
  using (owner_id = auth.uid()) with check (owner_id = auth.uid());

-- project-scoped tables
do $$ declare t text; begin
  foreach t in array array['documents','factory_runs','agent_definitions','regression_runs','artifacts','audit_logs'] loop
    execute format('drop policy if exists %I_owner on public.%I', t, t);
    execute format('create policy %I_owner on public.%I for all using (public.owns_project(project_id)) with check (public.owns_project(project_id))', t, t);
  end loop;
end $$;

-- run-scoped tables
do $$ declare t text; begin
  foreach t in array array['interview_records','requirements','approval_records','evaluation_datasets','evaluation_results',
                           'failure_records','scorecards','optimization_iterations','change_logs','baseline_comparisons'] loop
    execute format('drop policy if exists %I_owner on public.%I', t, t);
    execute format('create policy %I_owner on public.%I for all using (public.owns_run(run_id)) with check (public.owns_run(run_id))', t, t);
  end loop;
end $$;

drop policy if exists document_versions_owner on public.document_versions;
create policy document_versions_owner on public.document_versions for all
  using (exists (select 1 from public.documents d where d.id = document_id and public.owns_project(d.project_id)));

drop policy if exists agent_versions_owner on public.agent_versions;
create policy agent_versions_owner on public.agent_versions for all
  using (exists (select 1 from public.agent_definitions a where a.id = agent_definition_id and public.owns_project(a.project_id)));

drop policy if exists evaluation_cases_owner on public.evaluation_cases;
create policy evaluation_cases_owner on public.evaluation_cases for all
  using (exists (select 1 from public.evaluation_datasets d where d.id = dataset_id and public.owns_run(d.run_id)));

-- tool registry: readable by any signed-in user, writable only by service role
drop policy if exists tool_registry_read on public.tool_registry;
create policy tool_registry_read on public.tool_registry for select to authenticated using (true);

-- ------------------------------------------------------------------ storage buckets (private)
insert into storage.buckets (id, name, public, file_size_limit)
values ('documents', 'documents', false, 20971520),
       ('deliverables', 'deliverables', false, 52428800)
on conflict (id) do nothing;

-- object paths are "<project_id>/..."; owners can read their own project folder
drop policy if exists forgeai_documents_owner on storage.objects;
create policy forgeai_documents_owner on storage.objects for select to authenticated
  using (bucket_id in ('documents','deliverables')
         and public.owns_project(((storage.foldername(name))[1])::uuid));
