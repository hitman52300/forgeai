-- Removes the empty tables of an earlier prototype schema (alembic 0004) that
-- existed in the target Supabase project. Run only on a project you own and
-- only after confirming the tables are empty.
drop table if exists public.regression_results cascade;
drop table if exists public.scorecards cascade;
drop table if exists public.requirements_revisions cascade;
drop table if exists public.groundability_results cascade;
drop table if exists public.human_approvals cascade;
drop table if exists public.document_chunks cascade;
drop table if exists public.baseline_agents cascade;
drop table if exists public.agent_runs cascade;
drop table if exists public.refresh_tokens cascade;
drop table if exists public.roles cascade;
drop table if exists public.users cascade;
drop table if exists public.audit_events cascade;
drop table if exists public.alembic_version cascade;
drop table if exists public.optimization_iterations cascade;
drop table if exists public.evaluation_results cascade;
drop table if exists public.evaluation_cases cascade;
drop table if exists public.document_versions cascade;
drop table if exists public.baseline_comparisons cascade;
drop table if exists public.artifacts cascade;
drop table if exists public.agent_definitions cascade;
drop table if exists public.documents cascade;
drop table if exists public.projects cascade;
drop table if exists public.tool_registry cascade;
drop table if exists public.regression_runs cascade;
