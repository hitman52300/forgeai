"use client";
import { useEffect, useState } from "react";
import { api, download, get, post, waitJob } from "@/lib/api";
import { Alert, JobLog, PageHeader, RunPicker, Section, Spinner } from "@/components/ui";

const GROUPS: [string, string[]][] = [
  ["Reports", ["final_report", "regression", "baseline"]],
  ["Requirements and approval", ["requirements", "groundability", "approval", "interview", "tool_selection", "input_brief", "document_manifest"]],
  ["Agent definitions", ["agent_definition", "runnable_agent"]],
  ["Evaluation", ["evaluation_dataset", "evaluation_results", "scorecards", "failure_classification"]],
  ["Optimisation", ["iteration_logs", "change_log", "budget"]],
];

export default function Reports() {
  const [run, setRun] = useState<any>(null);
  const [arts, setArts] = useState<any[] | null>(null);
  const [md, setMd] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [log, setLog] = useState<string[] | null>(null);
  const [reg, setReg] = useState<any>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!run) return;
    setArts(null); setMd(""); setErr(""); setReg(null);
    get(`/runs/${run.run_id}/artifacts`).then((a) => {
      setArts(a);
      if (a.some((x: any) => x.name === "final_report.md"))
        api<Blob>(`/runs/${run.run_id}/artifacts/final_report.md`).then((b: any) => (b.text ? b.text() : JSON.stringify(b))).then(setMd).catch(() => null);
    }).catch((e) => setErr(e.message));
  }, [run]);

  async function regression() {
    const fd = new FormData(); files.forEach((f) => fd.append("files", f, f.name));
    try { setLog([]); const { job_id } = await post(`/runs/${run.run_id}/regression`, fd); setReg(await waitJob(job_id, setLog)); }
    catch (e: any) { setErr(e.message); } finally { setLog(null); }
  }

  const used = new Set<string>();
  return (
    <>
      <PageHeader eyebrow="Operate" title="Reports & Artifacts" subtitle="Every saved artifact of a run, available for download." />
      <RunPicker value={run?.run_id} onChange={setRun} />
      {err && <Alert kind="error">{err}</Alert>}
      {run && !arts && !err && <Spinner />}
      {arts && (
        <div className="grid gap-8 lg:grid-cols-[1fr_1.2fr]">
          <div>
            {GROUPS.map(([g, prefixes]) => {
              const items = arts.filter((x) => !used.has(x.name) && prefixes.some((p) => x.name.split("/").pop().startsWith(p) || x.name.startsWith(p)));
              items.forEach((x) => used.add(x.name));
              return items.length ? (
                <Section key={g} title={g}>
                  <div className="card divide-y divide-line">
                    {items.map((x) => (
                      <div key={x.name} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                        <span className="truncate font-mono text-xs">{x.name}</span>
                        <button className="btn shrink-0 px-3 py-1 text-xs" onClick={() => download(`/runs/${run.run_id}/artifacts/${x.name}`, x.name.split("/").pop())}>
                          Download · {(x.size / 1024).toFixed(1)} KB</button>
                      </div>))}
                  </div>
                </Section>) : null;
            })}
            {run.status === "completed" && (
              <Section title="Regression mode">
                <div className="card space-y-3 p-5 text-sm">
                  <p className="text-muted">Upload the complete, changed document set. Previous results are kept; a new regression report is created.</p>
                  <input type="file" multiple accept=".txt,.pdf,.docx,.csv" onChange={(e) => setFiles(Array.from(e.target.files || []))} />
                  <button className="btn-primary" disabled={!files.length || log !== null} onClick={regression}>Run regression</button>
                  {log && <JobLog title="Running regression tests" messages={log} />}
                  {reg && <pre className="overflow-auto rounded bg-canvas p-3 text-xs">{JSON.stringify(reg, null, 2)}</pre>}
                </div>
              </Section>
            )}
          </div>
          <Section title="Final report preview">
            {md ? <pre className="card max-h-[80vh] overflow-auto whitespace-pre-wrap p-5 text-xs leading-relaxed">{md}</pre>
              : <p className="text-sm text-muted">No final report for this run yet.</p>}
          </Section>
        </div>
      )}
    </>
  );
}
