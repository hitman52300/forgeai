"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { post, waitJob } from "@/lib/api";
import { Alert, JobLog, PageHeader } from "@/components/ui";

const TYPES = ".txt,.pdf,.docx,.csv";

export default function Create() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [brief, setBrief] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [cases, setCases] = useState(30);
  const [log, setLog] = useState<string[] | null>(null);
  const [err, setErr] = useState("");

  async function start(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    if (!name.trim() || !brief.trim() || !files.length) return setErr("Project name, brief and at least one document are required.");
    const fd = new FormData();
    fd.append("name", name); fd.append("brief", brief); fd.append("target_cases", String(cases));
    files.forEach((f) => fd.append("files", f, f.name));
    try {
      setLog([]);
      const { job_id } = await post("/projects/runs", fd);
      const out = await waitJob(job_id, setLog);
      localStorage.setItem("fa_run", out.run_id);
      router.push("/interview");
    } catch (ex: any) {
      setErr(ex.message); setLog(null);
    }
  }

  return (
    <>
      <PageHeader eyebrow="Build · Step 1" title="Create New Agent" subtitle="Describe the agent in one paragraph and upload its knowledge documents." />
      {err && <Alert kind="error">{err}</Alert>}
      {log && <JobLog title="Analysing documents and brief" messages={log} />}
      <form onSubmit={start} className="card grid gap-5 p-6 md:grid-cols-2">
        <div className="md:col-span-2">
          <label className="label">Project name</label>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Customer returns assistant" />
        </div>
        <div className="md:col-span-2">
          <label className="label">Brief</label>
          <textarea className="input min-h-36" value={brief} onChange={(e) => setBrief(e.target.value)}
            placeholder="Who the agent is for, what it must answer, the tone, and what it must not do." />
        </div>
        <div>
          <label className="label">Knowledge documents</label>
          <label className="flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-line-strong bg-canvas px-4 py-8 text-center text-sm text-muted hover:border-accent">
            <span className="font-medium text-navy">Choose files</span>
            <span className="mt-1 text-xs">Supported: {TYPES} · max 20 MB each</span>
            <input type="file" multiple accept={TYPES} className="hidden" onChange={(e) => setFiles(Array.from(e.target.files || []))} />
          </label>
          {files.length > 0 && (
            <ul className="mt-3 space-y-1 text-sm">
              {files.map((f) => <li key={f.name} className="flex justify-between"><span>{f.name}</span><span className="text-muted">{(f.size / 1024).toFixed(0)} KB</span></li>)}
            </ul>
          )}
        </div>
        <div>
          <label className="label">Evaluation cases to generate: {cases}</label>
          <input type="range" min={20} max={40} value={cases} onChange={(e) => setCases(Number(e.target.value))} className="w-full accent-[#2f6f73]" />
          <p className="mt-3 text-xs text-muted">At least 20 cases are always generated. Every expected fact is verified against the source documents.</p>
        </div>
        <div className="md:col-span-2">
          <button className="btn-primary" disabled={log !== null}>Start interview</button>
        </div>
      </form>
    </>
  );
}
