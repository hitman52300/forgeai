"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { get, pct } from "@/lib/api";
import { Alert, Badge, Kpi, PageHeader, Section, Spinner, Table } from "@/components/ui";

export default function Dashboard() {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    (async () => {
      const [runs, agents, health] = await Promise.all([get("/runs"), get("/agents"), get("/health").catch(() => ({}))]);
      const finals: any[] = [];
      for (const r of runs.filter((r: any) => r.status === "completed")) {
        const sc = await get(`/runs/${r.run_id}/evaluation/scorecards`).catch(() => []);
        const f = sc.find((s: any) => s.agent_version === r.final_agent_version);
        if (f) finals.push({ run: r, sc: f });
      }
      setData({ runs, agents, health, finals });
    })().catch((e) => setErr(e.message));
  }, []);

  if (err) return <Alert kind="error">{err}</Alert>;
  if (!data) return <Spinner label="Loading dashboard" />;
  const { runs, agents, health, finals } = data;
  const avg = finals.length ? finals.reduce((a: number, f: any) => a + f.sc.pass_rate, 0) / finals.length : null;
  const attention = [
    ...finals.filter((f: any) => f.sc.pass_rate < 0.85).map((f: any) => ({ r: f.run, why: `final pass rate ${pct(f.sc.pass_rate)} is below 85%` })),
    ...runs.filter((r: any) => ["awaiting_approval", "interviewing", "failed", "stopped"].includes(r.status))
      .map((r: any) => ({ r, why: { awaiting_approval: "requirements are waiting for approval", interviewing: "clarifying questions are waiting for answers" }[r.status as string] || r.stop_reason || r.status })),
  ];

  return (
    <>
      <PageHeader eyebrow="Overview" title="Dashboard" subtitle="Factory runs, generated agents and measured quality."
        actions={<Link href="/create" className="btn-primary">New agent</Link>} />
      <div className="mb-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label="Factory runs" value={runs.length} note="all time" />
        <Kpi label="Generated agents" value={agents.filter((a: any) => a.final_version).length} note="delivered" />
        <Kpi label="Avg. final pass rate" value={avg === null ? "n/a" : pct(avg)} note="measured, not estimated" />
        <Kpi label="Need attention" value={attention.length} note="below target or awaiting input" />
      </div>
      <div className="grid gap-8 lg:grid-cols-[1.6fr_1fr]">
        <div>
          <Section title="Recent projects">
            {runs.length ? (
              <Table head={["Project", "Status", "Final version", "Updated"]} rows={runs.slice(0, 10).map((r: any) => [
                <span className="font-medium text-navy">{r.project_name}</span>, <Badge s={r.status} />,
                r.final_agent_version ? `v${r.final_agent_version}` : "—", r.updated_at?.slice(0, 16).replace("T", " ")])} />
            ) : <Alert>No runs yet. Start one from Create New Agent.</Alert>}
          </Section>
          <Section title="Requiring attention">
            {attention.length ? (
              <div className="card divide-y divide-line">
                {attention.slice(0, 8).map(({ r, why }: any, i: number) => (
                  <div key={i} className="flex items-center gap-3 px-4 py-3 text-sm"><Badge s={r.status} />
                    <span className="font-medium text-navy">{r.project_name}</span><span className="text-muted">{why}</span></div>
                ))}
              </div>
            ) : <p className="text-sm text-muted">Nothing requires attention.</p>}
          </Section>
        </div>
        <div>
          <Section title="System">
            <div className="card space-y-2 p-4 text-sm">
              <div className="flex justify-between"><span className="text-muted">Storage</span><span>{health.storage_backend} ({health.database})</span></div>
              <div className="flex justify-between gap-3"><span className="text-muted">Agent model</span><code className="truncate text-xs">{health.llm_model}</code></div>
              <div className="flex justify-between gap-3"><span className="text-muted">Judge model</span><code className="truncate text-xs">{health.judge_model}</code></div>
              <div className="flex justify-between"><span className="text-muted">LLM provider</span><span>{health.ollama?.ok ? "reachable" : "check configuration"}</span></div>
            </div>
          </Section>
          <Section title="Recent activity">
            <div className="card divide-y divide-line">
              {runs.slice(0, 6).map((r: any) => {
                const st = r.stages || {};
                const last = Object.keys(st).reverse().find((k) => st[k] !== "pending");
                return last ? (
                  <div key={r.run_id} className="flex items-center gap-3 px-4 py-2.5 text-sm"><Badge s={st[last]} />
                    <span className="truncate">{r.project_name} · {last.replaceAll("_", " ")}</span></div>
                ) : null;
              })}
            </div>
          </Section>
        </div>
      </div>
    </>
  );
}
