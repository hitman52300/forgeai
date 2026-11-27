"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { get, post, waitJob } from "@/lib/api";
import { Alert, Badge, JobLog, Kpi, PageHeader, RunPicker, Spinner } from "@/components/ui";

const STAGES: [string, string][] = [["document_analysis", "Document Analysis"], ["interview", "Interview"], ["groundability", "Groundability"],
  ["requirements_approval", "Requirements Approval"], ["agent_generation", "Agent Generation"], ["evaluation_generation", "Evaluation Generation"],
  ["evaluation", "Evaluation"], ["optimization", "Optimization"], ["final_delivery", "Final Delivery"]];

export default function Execution() {
  const [run, setRun] = useState<any>(null);
  const [info, setInfo] = useState<any>(null);
  const [log, setLog] = useState<string[] | null>(null);
  const [err, setErr] = useState("");

  const refresh = (id: string) => get(`/runs/${id}`).then(setInfo).catch((e) => setErr(e.message));
  useEffect(() => { if (run) { setInfo(null); refresh(run.run_id); } }, [run]);
  useEffect(() => {
    if (!info || info.run.status !== "running") return;
    const t = setInterval(() => refresh(info.run.run_id), 8000);
    return () => clearInterval(t);
  }, [info]);

  async function execute() {
    setErr("");
    try {
      setLog([]);
      const { job_id } = await post(`/runs/${run.run_id}/execute`);
      await waitJob(job_id, (m) => { setLog(m); });
      setLog(null); refresh(run.run_id);
    } catch (e: any) { setErr(e.message); setLog(null); refresh(run.run_id); }
  }

  const r = info?.run;
  return (
    <>
      <PageHeader eyebrow="Build · Step 4" title="Factory Execution" subtitle="Stage statuses are read from the run record; a stage is shown completed only after it completed." />
      <RunPicker value={run?.run_id} onChange={setRun} />
      {err && <Alert kind="error">{err}</Alert>}
      {log && <JobLog title="Running the factory (unattended)" messages={log} />}
      {run && !info && !err && <Spinner />}
      {r && (
        <>
          <div className="mb-8 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
            {STAGES.map(([k, l], i) => (
              <div key={k} className="card flex min-h-36 flex-col p-4">
                <div className="text-[10px] font-semibold tracking-[0.12em] text-muted">STAGE {String(i + 1).padStart(2, "0")}</div>
                <div className="mb-2 mt-0.5 text-sm font-semibold text-navy">{l}</div>
                <div><Badge s={r.stages[k]} /></div>
                <div className="mt-2 line-clamp-3 text-xs text-muted" title={r.stage_messages[k] || ""}>{r.stage_messages[k] || ""}</div>
              </div>
            ))}
          </div>
          <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Kpi label="LLM calls" value={`${r.usage.llm_calls}`} note={`of ${r.budget.max_llm_calls} budget`} />
            <Kpi label="Tokens" value={(r.usage.prompt_tokens + r.usage.completion_tokens).toLocaleString()} note={`of ${r.budget.max_tokens.toLocaleString()}`} />
            <Kpi label="Elapsed" value={`${(r.usage.elapsed_seconds / 60).toFixed(1)} min`} note={`of ${Math.round(r.budget.max_seconds / 60)} min`} />
            <Kpi label="Optimisation iterations" value={`${r.usage.iterations}`} note={`of ${r.budget.max_iterations} max`} />
          </div>
          {r.stop_reason && <Alert>Stop reason: {r.stop_reason}</Alert>}
          {r.status === "approved" && (
            <div className="card flex flex-wrap items-center justify-between gap-4 p-5">
              <div className="text-sm">Requirements are approved. The remaining stages run unattended.</div>
              <button className="btn-primary" disabled={log !== null} onClick={execute}>Run factory (unattended)</button>
            </div>
          )}
          {["awaiting_approval", "interviewing"].includes(r.status) && (
            <Alert kind="warn">Awaiting human approval of the requirements. Execution is blocked until then. <Link className="ml-1 font-semibold underline" href="/requirements">Review requirements</Link></Alert>
          )}
          {r.status === "running" && !log && <Alert>This run is executing. This page refreshes every few seconds.</Alert>}
        </>
      )}
    </>
  );
}
