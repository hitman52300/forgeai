"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { get, post } from "@/lib/api";
import { Alert, Badge, PageHeader, RunPicker, Spinner, Table } from "@/components/ui";

const TEXT = ["project_name", "agent_purpose", "target_audience", "scope", "tone", "response_format"];
const LISTS = ["supported_topics", "must_answer_topics", "must_refuse_topics", "required_tools", "explicit_limitations",
  "unresolved_ambiguities", "acceptance_criteria"];
const label = (k: string) => k.replaceAll("_", " ").replace(/^\w/, (c) => c.toUpperCase());

export default function Requirements() {
  const [run, setRun] = useState<any>(null);
  const [data, setData] = useState<any>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [hist, setHist] = useState<any[]>([]);
  const [tab, setTab] = useState<"req" | "ground" | "hist">("req");
  const [approver, setApprover] = useState("");
  const [comment, setComment] = useState("");
  const [msg, setMsg] = useState<{ k: "ok" | "error"; t: string } | null>(null);
  const [busy, setBusy] = useState(false);

  function load(r: any) {
    setData(null); setMsg(null);
    get(`/runs/${r.run_id}/requirements`).then((d) => {
      setData(d);
      const c = d.current || {};
      setForm(Object.fromEntries([...TEXT.map((k) => [k, c[k] ?? ""]), ...LISTS.map((k) => [k, (c[k] || []).join("\n")])]));
    }).catch((e) => setMsg({ k: "error", t: e.message }));
    get(`/runs/${r.run_id}/approval/history`).then(setHist).catch(() => setHist([]));
  }
  useEffect(() => { if (run) load(run); }, [run]);

  const cur = data?.current;
  const edits: Record<string, any> = {};
  if (cur) {
    TEXT.forEach((k) => { if (form[k] !== cur[k]) edits[k] = form[k]; });
    LISTS.forEach((k) => {
      const items = (form[k] || "").split("\n").map((s) => s.trim()).filter(Boolean);
      if (JSON.stringify(items) !== JSON.stringify(cur[k] || [])) edits[k] = items;
    });
  }
  const can = run?.status === "awaiting_approval";

  async function decide(decision: "approved" | "rejected") {
    if (!approver.trim()) return setMsg({ k: "error", t: "Approver name is required." });
    setBusy(true); setMsg(null);
    try {
      const r = await post(`/runs/${run.run_id}/approval`, { decision, approver_name: approver, edits, comment });
      setMsg({ k: "ok", t: `${r.decision === "approved" ? "Approved" : "Rejected"} by ${r.approver} at ${r.timestamp.slice(0, 19)} UTC · ${r.diff.length} field(s) changed.` });
      setRun({ ...run, status: decision === "approved" ? "approved" : "awaiting_approval" });
    } catch (e: any) { setMsg({ k: "error", t: e.message }); } finally { setBusy(false); }
  }

  return (
    <>
      <PageHeader eyebrow="Build · Step 3" title="Requirements Review" subtitle="Mandatory human checkpoint. Agent generation cannot start before approval." />
      <RunPicker value={run?.run_id} onChange={setRun} />
      {msg && <Alert kind={msg.k}>{msg.t} {msg.k === "ok" && run?.status === "approved" && <Link className="ml-2 font-semibold underline" href="/execution">Go to Factory Execution</Link>}</Alert>}
      {run && !data && !msg && <Spinner />}
      {data && !cur && <Alert>Requirements have not been generated for this run yet.</Alert>}
      {cur && (
        <>
          <div className="mb-5 flex items-center gap-3 text-sm"><span className="text-muted">Status</span><Badge s={run.status} /></div>
          <div className="mb-5 flex gap-1 border-b border-line">
            {([["req", "Requirements"], ["ground", "Groundability matrix"], ["hist", "Approval history"]] as const).map(([k, t]) => (
              <button key={k} onClick={() => setTab(k)} className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${tab === k ? "border-accent text-navy" : "border-transparent text-muted hover:text-navy"}`}>{t}</button>
            ))}
          </div>

          {tab === "req" && (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                {[...TEXT, ...LISTS].map((k) => (
                  <div key={k} className={k === "scope" || k === "agent_purpose" ? "md:col-span-2" : ""}>
                    <label className="label">{label(k)}{LISTS.includes(k) && <span className="normal-case tracking-normal"> (one per line)</span>}</label>
                    <textarea className={`input ${LISTS.includes(k) ? "min-h-28" : "min-h-14"}`} disabled={!can} value={form[k] || ""}
                      onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
                  </div>
                ))}
              </div>
              <p className="mt-4 text-sm"><span className="text-muted">Knowledge sources (derived, not editable):</span> {cur.knowledge_sources.join(", ")}</p>
              {cur.decision_notes?.length > 0 && <p className="mt-1 text-xs text-muted">Factory notes: {cur.decision_notes.join(" · ")}</p>}
              <div className="card mt-6 grid gap-4 p-5 md:grid-cols-[1fr_1fr_auto]">
                <div><label className="label">Approver name</label><input className="input" disabled={!can} value={approver} onChange={(e) => setApprover(e.target.value)} /></div>
                <div><label className="label">Comment</label><input className="input" disabled={!can} value={comment} onChange={(e) => setComment(e.target.value)} /></div>
                <div className="flex items-end gap-2">
                  <button className="btn" disabled={!can || busy} onClick={() => decide("rejected")}>Reject</button>
                  <button className="btn-primary" disabled={!can || busy} onClick={() => decide("approved")}>Approve</button>
                </div>
                <div className="text-xs text-muted md:col-span-3">
                  {Object.keys(edits).length ? `Pending edits: ${Object.keys(edits).join(", ")}` : "No edits."}
                  {!can && ` Decisions are only possible while the run is awaiting approval (now: ${run.status.replaceAll("_", " ")}).`}
                </div>
              </div>
            </>
          )}

          {tab === "ground" && (
            <>
              <Table head={["Requested topic", "Evidence", "Status", "Best similarity", "Rationale"]} rows={data.groundability.topics.map((t: any) => [
                <span className="font-medium text-navy">{t.topic}</span>,
                t.status === "unsupported" ? "No supporting document" : [...new Set(t.evidence.slice(0, 3).map((e: any) => `${e.source_filename} (${e.location})`))].join(", "),
                <Badge s={t.status === "supported" ? "completed" : t.status === "unsupported" ? "failed" : "awaiting_approval"} />,
                t.retrieval_max_score.toFixed(2), <span className="text-xs text-muted">{t.rationale}</span>])} />
              {data.groundability.topics.some((t: any) => t.status === "unsupported") && (
                <div className="mt-4"><Alert kind="warn">Unsupported topics are refused by the agent. Upload documents covering them in a new run if they are needed.</Alert></div>
              )}
              <h3 className="mb-2 mt-6 text-sm font-semibold text-navy">Tool decisions</h3>
              <ul className="space-y-1 text-sm">{(data.tool_selection || []).map((t: any) => (
                <li key={t.tool}><code className="text-xs">{t.tool}</code> — {t.selected ? "attached" : "not attached"}: <span className="text-muted">{t.reason}</span></li>))}</ul>
            </>
          )}

          {tab === "hist" && (
            <div className="space-y-4">
              {!hist.length && <p className="text-sm text-muted">No decisions recorded yet.</p>}
              {[...hist].reverse().map((h, i) => (
                <div key={i} className="card p-5">
                  <div className="flex flex-wrap items-center gap-3 text-sm">
                    <Badge s={h.decision === "approved" ? "completed" : "failed"} />
                    <span className="font-medium text-navy">{h.approver}</span>
                    <span className="text-muted">{h.timestamp.slice(0, 19).replace("T", " ")} UTC · requirements v{h.requirements_version}</span>
                  </div>
                  {h.comment && <p className="mt-2 text-sm text-muted">{h.comment}</p>}
                  <details className="mt-3 text-sm"><summary className="cursor-pointer text-navy">Version comparison ({h.diff.length} changed field(s))</summary>
                    <div className="mt-3 space-y-3">{h.diff.map((d: any) => (
                      <div key={d.field}><div className="font-medium">{label(d.field)}</div>
                        {"added" in d ? <div className="text-xs text-muted">added: {JSON.stringify(d.added)} · removed: {JSON.stringify(d.removed)}</div>
                          : <div className="grid gap-2 text-xs md:grid-cols-2"><div className="rounded bg-[#f9ecec] p-2">{String(d.before)}</div><div className="rounded bg-[#e8f1ef] p-2">{String(d.after)}</div></div>}
                      </div>))}</div>
                  </details>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </>
  );
}
