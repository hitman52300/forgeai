"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { get, post, waitJob } from "@/lib/api";
import { Alert, JobLog, PageHeader, RunPicker, Spinner } from "@/components/ui";

export default function Interview() {
  const router = useRouter();
  const [run, setRun] = useState<any>(null);
  const [iv, setIv] = useState<any>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [log, setLog] = useState<string[] | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!run) return;
    setIv(null);
    setErr("");
    get(`/runs/${run.run_id}/interview`).then((d) => {
      if (!d?.analysis) {
        setErr("This run has no interview yet. If it was interrupted, create the agent again.");
        return;
      }
      setIv(d);
      setAnswers(Object.fromEntries((d.analysis.questions || []).map((q: any) => [q.question_id, q.answer || ""])));
    }).catch((e) => setErr(e.message));
  }, [run]);

  async function submit() {
    setErr("");
    try {
      setLog([]);
      const { job_id } = await post(`/runs/${run.run_id}/interview/answers`, { answers });
      await waitJob(job_id, setLog);
      router.push("/requirements");
    } catch (e: any) { setErr(e.message); setLog(null); }
  }

  const a = iv?.analysis;
  const editable = run?.status === "interviewing";
  const answered = a ? (a.questions || []).filter((q: any) => (answers[q.question_id] || "").trim()).length : 0;
  return (
    <>
      <PageHeader eyebrow="Build · Step 2" title="Interview" subtitle="Up to five clarifying questions generated from the brief and the documents." />
      <RunPicker value={run?.run_id} onChange={setRun} />
      {err && <Alert kind="error">{err}</Alert>}
      {log && <JobLog title="Checking groundability and writing requirements" messages={log} />}
      {run && !iv && !err && <Spinner />}
      {a && (
        <>
          <div className="mb-6 grid gap-4 md:grid-cols-2">
            <div className="card p-5 text-sm">
              <div className="label">Understood purpose</div><p className="mb-3">{a.agent_purpose}</p>
              <div className="label">Audience</div><p>{a.target_audience}</p>
            </div>
            <div className="card p-5 text-sm">
              <div className="label">Requested topics</div>
              <div className="mb-3 flex flex-wrap gap-1.5">{a.requested_topics.map((t: string) => <span key={t} className="rounded-full bg-accent-soft px-2.5 py-0.5 text-xs text-navy">{t}</span>)}</div>
              {a.ambiguities?.length > 0 && <><div className="label">Ambiguities</div><ul className="list-disc pl-5 text-muted">{a.ambiguities.map((x: string) => <li key={x}>{x}</li>)}</ul></>}
            </div>
          </div>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-base font-semibold text-navy">Clarifying questions ({a.questions.length} of max 5)</h2>
            <span className="text-sm text-muted">{answered}/{a.questions.length} answered</span>
          </div>
          <div className="mb-5 h-1.5 overflow-hidden rounded-full bg-line">
            <div className="h-full bg-accent transition-all" style={{ width: `${a.questions.length ? (answered / a.questions.length) * 100 : 100}%` }} />
          </div>
          <div className="space-y-4">
            {a.questions.map((q: any, i: number) => (
              <div key={q.question_id} className="card p-5">
                <div className="mb-1 text-xs font-semibold text-accent">Question {i + 1}</div>
                <div className="mb-1 font-medium text-navy">{q.question}</div>
                {q.reason && <div className="mb-3 text-xs text-muted">{q.reason}</div>}
                <textarea className="input min-h-20" disabled={!editable} value={answers[q.question_id] || ""}
                  onChange={(e) => setAnswers({ ...answers, [q.question_id]: e.target.value })} />
              </div>
            ))}
            {!a.questions.length && <Alert>No clarification was needed.</Alert>}
          </div>
          {iv.dropped_questions?.length > 0 && (
            <details className="card mt-4 p-4 text-sm"><summary className="cursor-pointer font-medium text-navy">{iv.dropped_questions.length} candidate question(s) dropped</summary>
              <ul className="mt-2 list-disc pl-5 text-muted">{iv.dropped_questions.map((d: any, i: number) => <li key={i}>{d.question} — <i>{d.reason}</i> {d.evidence || ""}</li>)}</ul>
            </details>
          )}
          <div className="mt-6">
            {editable ? <button className="btn-primary" disabled={log !== null} onClick={submit}>Submit answers and build requirements</button>
              : <p className="text-sm text-muted">Run status is “{run.status.replaceAll("_", " ")}”; answers can no longer be changed.</p>}
          </div>
        </>
      )}
    </>
  );
}
