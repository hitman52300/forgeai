"use client";
import { ReactNode, useEffect, useState } from "react";
import { get } from "@/lib/api";

export function PageHeader({ eyebrow, title, subtitle, actions }: { eyebrow?: string; title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-4 border-b border-line pb-5">
      <div>
        {eyebrow && <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-accent">{eyebrow}</div>}
        <h1 className="text-[26px] font-bold tracking-tight text-navy">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-muted">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}

const BADGE: Record<string, string> = {
  completed: "bg-[#e8f1ef] border-[#c4dad5] text-[#1f5450]",
  running: "bg-[#eaf0f8] border-[#c9d7ea] text-[#24476f]",
  failed: "bg-[#f9ecec] border-[#e6c7c7] text-[#7a2e2e]",
  stopped: "bg-[#f9ecec] border-[#e6c7c7] text-[#7a2e2e]",
  awaiting_approval: "bg-[#fbf4e6] border-[#ebd7ae] text-[#7a5a1e]",
  interviewing: "bg-[#fbf4e6] border-[#ebd7ae] text-[#7a5a1e]",
  approved: "bg-[#eaf0f8] border-[#c9d7ea] text-[#24476f]",
};

export function Badge({ s }: { s: string }) {
  return (
    <span className={`inline-block whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium ${BADGE[s] || "border-line bg-canvas text-muted"}`}>
      {String(s).replaceAll("_", " ")}
    </span>
  );
}

export function Kpi({ label, value, note }: { label: string; value: ReactNode; note?: string }) {
  return (
    <div className="card p-5">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">{label}</div>
      <div className="mt-2 text-[28px] font-bold tracking-tight text-navy">{value}</div>
      <div className="mt-0.5 text-xs text-muted">{note || " "}</div>
    </div>
  );
}

export function Section({ title, children, right }: { title: string; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="mb-8">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-base font-semibold text-navy">{title}</h2>
        {right}
      </div>
      {children}
    </section>
  );
}

export function Alert({ kind = "info", children }: { kind?: "info" | "error" | "warn" | "ok"; children: ReactNode }) {
  const c = { info: "border-[#c9d7ea] bg-[#eaf0f8] text-[#24476f]", error: "border-[#e6c7c7] bg-[#f9ecec] text-[#7a2e2e]",
    warn: "border-[#ebd7ae] bg-[#fbf4e6] text-[#7a5a1e]", ok: "border-[#c4dad5] bg-[#e8f1ef] text-[#1f5450]" }[kind];
  return <div className={`mb-4 rounded-lg border px-4 py-3 text-sm ${c}`}>{children}</div>;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-6 text-sm text-muted">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-line-strong border-t-accent" />
      {label || "Loading"}
    </div>
  );
}

export function JobLog({ messages, title }: { messages: string[]; title: string }) {
  return (
    <div className="card mb-4 p-4">
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-navy">
        <span className="h-3 w-3 animate-spin rounded-full border-2 border-line-strong border-t-accent" /> {title}
      </div>
      <div className="max-h-48 overflow-auto font-mono text-xs text-muted">
        {messages.slice(-12).map((m, i) => <div key={i}>{m}</div>)}
      </div>
    </div>
  );
}

export function useRuns() {
  const [runs, setRuns] = useState<any[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { get("/runs").then(setRuns).catch((e) => setError(e.message)); }, []);
  return { runs, error };
}

export function RunPicker({ value, onChange, filter }: { value?: string; onChange: (r: any) => void; filter?: (r: any) => boolean }) {
  const { runs, error } = useRuns();
  const list = (runs || []).filter((r) => !filter || filter(r));
  useEffect(() => {
    if (!list.length) return;
    const saved = value || (typeof window !== "undefined" ? localStorage.getItem("fa_run") : null);
    onChange(list.find((r) => r.run_id === saved) || list[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runs]);
  if (error) return <Alert kind="error">{error}</Alert>;
  if (!runs) return <Spinner label="Loading runs" />;
  if (!list.length) return <Alert>No matching factory runs yet.</Alert>;
  return (
    <div className="mb-6 max-w-xl">
      <label className="label">Factory run</label>
      <select className="input" value={value || ""} onChange={(e) => {
        const r = list.find((x) => x.run_id === e.target.value);
        try { localStorage.setItem("fa_run", e.target.value); } catch { /* storage unavailable */ }
        onChange(r);
      }}>
        {list.map((r) => (
          <option key={r.run_id} value={r.run_id}>{r.project_name} · {r.status.replaceAll("_", " ")} · {r.run_id.slice(0, 8)}</option>
        ))}
      </select>
    </div>
  );
}

export function Table({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <div className="card overflow-x-auto">
      <table className="w-full border-collapse">
        <thead><tr>{head.map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i} className="hover:bg-canvas/60">{r.map((c, j) => <td key={j} className="td">{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}
