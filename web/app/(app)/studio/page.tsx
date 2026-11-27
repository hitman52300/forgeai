"use client";
import { useEffect, useState } from "react";
import { get } from "@/lib/api";
import { Alert, PageHeader, Section, Spinner, Table } from "@/components/ui";

function Json({ v }: { v: any }) {
  return <pre className="overflow-auto rounded-lg bg-canvas p-3 text-xs">{JSON.stringify(v, null, 2)}</pre>;
}

export default function Studio() {
  const [agents, setAgents] = useState<any[] | null>(null);
  const [aid, setAid] = useState("");
  const [vers, setVers] = useState<any[]>([]);
  const [vi, setVi] = useState(0);
  const [err, setErr] = useState("");

  useEffect(() => { get("/agents").then((a) => { setAgents(a); if (a[0]) setAid(a[0].id); }).catch((e) => setErr(e.message)); }, []);
  const agent = agents?.find((a) => a.id === aid);
  useEffect(() => {
    if (!aid) return;
    get(`/agents/${aid}/versions`).then((v) => {
      setVers(v);
      const f = v.findIndex((x: any) => x.version === agent?.final_version);
      setVi(f >= 0 ? f : v.length - 1);
    }).catch((e) => setErr(e.message));
  }, [aid]); // eslint-disable-line react-hooks/exhaustive-deps

  const d = vers[vi]?.definition;
  function dl() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(d, null, 2)], { type: "application/json" }));
    const a = document.createElement("a"); a.href = url; a.download = `${d.agent_name.replaceAll(" ", "_")}_v${d.version}.json`; a.click(); URL.revokeObjectURL(url);
  }

  return (
    <>
      <PageHeader eyebrow="Quality" title="Agent Studio" subtitle="Inspect generated agent definitions and their version history."
        actions={d && <button className="btn" onClick={dl}>Download definition (JSON)</button>} />
      {err && <Alert kind="error">{err}</Alert>}
      {!agents && !err && <Spinner />}
      {agents && !agents.length && <Alert>No agents have been generated yet.</Alert>}
      {agents && agents.length > 0 && (
        <div className="mb-6 grid max-w-3xl gap-4 md:grid-cols-[2fr_1fr]">
          <div><label className="label">Agent</label>
            <select className="input" value={aid} onChange={(e) => setAid(e.target.value)}>
              {agents.map((a) => <option key={a.id} value={a.id}>{a.agent_name} · {a.project_name} ({a.origin})</option>)}
            </select></div>
          <div><label className="label">Version</label>
            <select className="input" value={vi} onChange={(e) => setVi(Number(e.target.value))}>
              {vers.map((v, i) => <option key={i} value={i}>v{v.version}{v.version === agent?.final_version ? " (final)" : ""}</option>)}
            </select></div>
        </div>
      )}
      {d && (
        <>
          <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
            <div>
              <div className="card mb-4 p-5 text-sm">
                <h2 className="text-lg font-semibold text-navy">{d.agent_name} <span className="text-muted">v{d.version}</span></h2>
                <p className="mt-2"><span className="text-muted">Purpose:</span> {d.purpose}</p>
                <p><span className="text-muted">Audience:</span> {d.audience}</p>
                <p><span className="text-muted">Tone:</span> {d.tone}</p>
                <p><span className="text-muted">Model:</span> <code className="text-xs">{d.model}</code></p>
                <p><span className="text-muted">Tools:</span> {d.tools.length ? d.tools.map((t: string) => <code key={t} className="mr-1 rounded bg-canvas px-1.5 text-xs">{t}</code>) : "none"}</p>
              </div>
              <Section title="System prompt"><pre className="card max-h-[520px] overflow-auto whitespace-pre-wrap p-5 text-xs leading-relaxed">{d.system_prompt}</pre></Section>
            </div>
            <div>
              <Section title="Retrieval configuration"><Json v={Object.fromEntries(Object.entries(d.retrieval_config).filter(([k]) => k !== "separators"))} /></Section>
              <Section title="Output contract"><Json v={d.output_contract} /></Section>
              <Section title="Refusal policy"><Json v={d.refusal_policy} /></Section>
              <Section title="Runtime options"><Json v={d.runtime_options || {}} /></Section>
            </div>
          </div>
          <Section title="Version history">
            <Table head={["Version", "Parent", "Created", "Changes"]} rows={vers.map((x) => [`v${x.version}`, x.parent_version ? `v${x.parent_version}` : "—",
              x.created_at?.slice(0, 16).replace("T", " "), <span className="text-xs">{(x.change_summary || []).join(" | ").slice(0, 300)}</span>])} />
          </Section>
        </>
      )}
    </>
  );
}
