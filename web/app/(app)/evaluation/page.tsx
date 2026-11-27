"use client";
import { useEffect, useMemo, useState } from "react";
import { get, pct } from "@/lib/api";
import { Alert, Badge, Kpi, PageHeader, RunPicker, Section, Spinner, Table } from "@/components/ui";

const METRICS = ["grounding", "factual_correctness", "citation_correctness", "refusal_correctness", "scope_adherence", "output_contract"];

export default function Evaluation() {
  const [run, setRun] = useState<any>(null);
  const [scs, setScs] = useState<any[] | null>(null);
  const [idx, setIdx] = useState(0);
  const [res, setRes] = useState<any[]>([]);
  const [ds, setDs] = useState<Record<string, any>>({});
  const [its, setIts] = useState<any>({ iterations: [] });
  const [onlyFail, setOnlyFail] = useState(false);
  const [sel, setSel] = useState<string | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!run) return;
    setScs(null); setSel(null);
    Promise.all([get(`/runs/${run.run_id}/evaluation/scorecards`), get(`/runs/${run.run_id}/evaluation/dataset`).catch(() => null),
      get(`/runs/${run.run_id}/evaluation/iterations`).catch(() => ({ iterations: [] }))]).then(([s, d, i]) => {
      setScs(s);
      const f = s.findIndex((x: any) => x.agent_version === run.final_agent_version);
      setIdx(f >= 0 ? f : Math.max(0, s.length - 1));
      setDs(Object.fromEntries((d?.cases || []).map((c: any) => [c.test_id, c])));
      setIts(i);
    }).catch((e) => setErr(e.message));
  }, [run]);

  const sc = scs?.[idx];
  useEffect(() => {
    if (!sc) return;
    get(`/runs/${run.run_id}/evaluation/results/${sc.iteration === 0 ? "initial" : sc.iteration}`).then(setRes).catch(() => setRes([]));
  }, [sc, run]);
  const rows = useMemo(() => res.filter((r) => !onlyFail || !r.passed), [res, onlyFail]);
  const cur = rows.find((r) => r.test_id === sel);
  const maxFail = sc ? Math.max(1, ...Object.values(sc.failure_categories as Record<string, number>)) : 1;

  return (
    <>
      <PageHeader eyebrow="Quality" title="Evaluation Dashboard" subtitle="Measured results only. Pass rate, individual metrics and the composite are reported separately." />
      <RunPicker value={run?.run_id} onChange={setRun} />
      {err && <Alert kind="error">{err}</Alert>}
      {run && !scs && !err && <Spinner />}
      {scs && !scs.length && <Alert>No evaluation has completed for this run yet.</Alert>}
      {sc && (
        <>
          <div className="mb-6 max-w-sm">
            <label className="label">Scorecard</label>
            <select className="input" value={idx} onChange={(e) => { setIdx(Number(e.target.value)); setSel(null); }}>
              {scs.map((s, i) => <option key={i} value={i}>iteration {s.iteration} (v{s.agent_version}){s.agent_version === run.final_agent_version ? " · final" : ""}</option>)}
            </select>
          </div>
          <div className="mb-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Kpi label="Total cases" value={sc.total_cases} />
            <Kpi label="Passed" value={sc.passed_cases} />
            <Kpi label="Failed" value={sc.failed_cases} />
            <Kpi label="Case pass rate" value={pct(sc.pass_rate)} note="all criteria met" />
          </div>
          <div className="grid gap-8 lg:grid-cols-2">
            <Section title="Quality metrics">
              <Table head={["Metric", "Score", "Cases applicable"]} rows={[
                ...METRICS.map((m) => [m.replaceAll("_", " "), <span className="font-semibold">{pct(sc.metrics[m])}</span>, sc.metric_counts[m] ?? 0]),
                [<i>composite (derived)</i>, pct(sc.composite_score), ""]]} />
              <p className="mt-2 text-xs text-muted">{sc.composite_formula}</p>
            </Section>
            <div>
              <Section title="Failure categories">
                <div className="card space-y-2 p-4">
                  {Object.keys(sc.failure_categories).length ? Object.entries(sc.failure_categories as Record<string, number>).map(([k, v]) => (
                    <div key={k} className="text-sm">
                      <div className="flex justify-between"><span>{k.replaceAll("_", " ")}</span><span className="text-muted">{v}</span></div>
                      <div className="mt-1 h-2 rounded-full bg-line"><div className="h-2 rounded-full bg-accent" style={{ width: `${(v / maxFail) * 100}%` }} /></div>
                    </div>)) : <p className="text-sm text-muted">No failures in this scorecard.</p>}
                </div>
              </Section>
              <Section title="By category">
                <Table head={["Category", "Passed", "Total", "Pass rate"]} rows={Object.entries(sc.by_category).map(([k, v]: any) => [k.replaceAll("_", " "), v.passed, v.total, pct(v.pass_rate)])} />
              </Section>
            </div>
          </div>

          <Section title="Iteration comparison">
            <div className="card mb-4 flex items-end gap-6 overflow-x-auto p-5">
              {scs.map((s, i) => (
                <div key={i} className="flex min-w-20 flex-col items-center">
                  <div className="mb-1 text-xs font-semibold text-navy">{pct(s.pass_rate)}</div>
                  <div className="flex h-32 w-10 items-end rounded bg-canvas"><div className="w-10 rounded bg-accent" style={{ height: `${s.pass_rate * 100}%` }} /></div>
                  <div className="mt-2 text-xs text-muted">it{s.iteration} · v{s.agent_version}</div>
                </div>
              ))}
            </div>
            {its.iterations.map((rec: any) => (
              <details key={rec.iteration} className="card mb-3 p-4 text-sm">
                <summary className="cursor-pointer font-medium text-navy">Iteration {rec.iteration}: v{rec.from_version} → {rec.to_version ? `v${rec.to_version}` : "—"} · {rec.decision} ({rec.decision_reason})</summary>
                <p className="mt-2">Pass rate {pct(rec.score_before)} → {pct(rec.score_after)}; targets: {rec.failure_categories.join(", ")}</p>
                {rec.changes_made.length > 0 && <ul className="mt-2 list-disc pl-5 text-xs">{rec.changes_made.map((c: string, i: number) => <li key={i}>{c}</li>)}</ul>}
                <p className="mt-2 text-xs text-muted">Newly failing: {rec.regression_results.filter((x: any) => x.now === "fail").map((x: any) => x.test_id).join(", ") || "none"}</p>
              </details>
            ))}
          </Section>

          <Section title="Case-level results" right={<label className="flex items-center gap-2 text-sm text-muted"><input type="checkbox" checked={onlyFail} onChange={(e) => setOnlyFail(e.target.checked)} /> failed only</label>}>
            <div className="card max-h-[420px] overflow-auto">
              <table className="w-full border-collapse">
                <thead className="sticky top-0"><tr>{["Test", "Category", "Result", "Refused", "Failure", "Question"].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
                <tbody>{rows.map((r) => (
                  <tr key={r.test_id} onClick={() => setSel(r.test_id)} className={`cursor-pointer hover:bg-canvas ${sel === r.test_id ? "bg-accent-soft" : ""}`}>
                    <td className="td font-mono text-xs">{r.test_id}</td><td className="td">{r.category.replaceAll("_", " ")}</td>
                    <td className="td"><Badge s={r.passed ? "completed" : "failed"} /></td><td className="td">{r.answer.refused ? "yes" : "no"}</td>
                    <td className="td text-xs">{r.failure_categories.join(", ")}</td><td className="td">{r.question}</td></tr>))}</tbody>
              </table>
            </div>
          </Section>
          {cur && (
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="card space-y-3 p-5 text-sm">
                <div><div className="label">Question</div>{cur.question}</div>
                <div><div className="label">Expected behaviour</div>{ds[cur.test_id]?.expected_behavior}</div>
                <div><div className="label">Expected facts</div>{(ds[cur.test_id]?.expected_facts || []).join("; ") || "none"}</div>
                <div><div className="label">Answer</div>{cur.answer.answer}</div>
                <div><div className="label">Citations</div>{cur.answer.citations.join(", ") || "none"}</div>
                {cur.answer.refused && <div><div className="label">Refusal reason</div>{cur.answer.refusal_reason}</div>}
                {cur.failure_explanation && <Alert kind="error">{cur.failure_explanation}</Alert>}
              </div>
              <div className="card space-y-3 p-5 text-sm">
                <div className="label">Metric explanations</div>
                {Object.entries(cur.metrics).map(([m, v]: any) => (
                  <div key={m}><span className="font-medium">{m.replaceAll("_", " ")}</span>: {v.applicable ? v.score : "n/a"} <span className="text-xs text-muted">({v.method}) {v.explanation?.slice(0, 220)}</span></div>))}
                <div className="label pt-2">Source evidence</div>
                {cur.retrieved.map((e: any, i: number) => (
                  <div key={i} className="rounded-lg bg-canvas p-3 text-xs"><div className="mb-1 font-semibold text-navy">{e.source_filename} ({e.location}, similarity {e.score.toFixed(2)})</div>{e.excerpt.slice(0, 280)}</div>))}
              </div>
            </div>
          )}
        </>
      )}
    </>
  );
}
