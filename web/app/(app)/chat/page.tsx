"use client";
import { useEffect, useRef, useState } from "react";
import { api, get, post } from "@/lib/api";
import { Alert, PageHeader, Spinner } from "@/components/ui";

type Turn = { q: string; r?: any; err?: string };

export default function Chat() {
  const [agents, setAgents] = useState<any[] | null>(null);
  const [aid, setAid] = useState("");
  const [turns, setTurns] = useState<Record<string, Turn[]>>({}); // history per agent: never mixed
  const [sid, setSid] = useState<Record<string, string>>({});
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    get("/agents").then((a) => {
      const ok = a.filter((x: any) => x.final_version || x.origin === "human_baseline");
      setAgents(ok); if (ok[0]) setAid(ok[0].id);
    }).catch((e) => setErr(e.message));
  }, []);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [turns, aid]);

  const session = sid[aid] || (aid ? `s-${aid.slice(0, 8)}-${Date.now()}` : "");
  useEffect(() => { if (aid && !sid[aid]) setSid({ ...sid, [aid]: session }); }, [aid]); // eslint-disable-line react-hooks/exhaustive-deps
  const list = turns[aid] || [];

  async function ask(e: React.FormEvent) {
    e.preventDefault();
    const question = q.trim();
    if (!question || busy) return;
    setQ(""); setBusy(true);
    const idx = list.length;
    setTurns((t) => ({ ...t, [aid]: [...(t[aid] || []), { q: question }] }));
    try {
      const r = await post(`/agents/${aid}/chat`, { question, session_id: sid[aid] || session });
      setTurns((t) => ({ ...t, [aid]: (t[aid] || []).map((x, i) => (i === idx ? { ...x, r } : x)) }));
    } catch (ex: any) {
      setTurns((t) => ({ ...t, [aid]: (t[aid] || []).map((x, i) => (i === idx ? { ...x, err: ex.message } : x)) }));
    } finally { setBusy(false); }
  }

  async function reset() {
    if (sid[aid]) await api(`/agents/${aid}/chat/${sid[aid]}`, { method: "DELETE" }).catch(() => null);
    setTurns({ ...turns, [aid]: [] }); setSid({ ...sid, [aid]: `s-${aid.slice(0, 8)}-${Date.now()}` });
  }

  return (
    <>
      <PageHeader eyebrow="Operate" title="Agent Chat Runner" subtitle="Generic runtime: any delivered agent, its own knowledge base, its own conversation history." />
      {err && <Alert kind="error">{err}</Alert>}
      {!agents && !err && <Spinner />}
      {agents && !agents.length && <Alert>No delivered agents yet.</Alert>}
      {agents && agents.length > 0 && (
        <>
          <div className="mb-4 flex flex-wrap items-end gap-3">
            <div className="min-w-80 flex-1"><label className="label">Agent</label>
              <select className="input" value={aid} onChange={(e) => setAid(e.target.value)}>
                {agents.map((a) => <option key={a.id} value={a.id}>{a.agent_name} · {a.project_name} (v{a.final_version || a.latest_version})</option>)}
              </select></div>
            <button className="btn" onClick={reset}>New conversation</button>
          </div>
          <div className="card flex h-[60vh] flex-col">
            <div className="flex-1 space-y-5 overflow-y-auto p-5">
              {!list.length && <p className="pt-10 text-center text-sm text-muted">Ask a question. Answers come only from this agent's approved documents and attached tools.</p>}
              {list.map((t, i) => (
                <div key={i} className="space-y-2">
                  <div className="ml-auto w-fit max-w-[80%] rounded-2xl rounded-br-sm bg-navy px-4 py-2.5 text-sm text-white">{t.q}</div>
                  {!t.r && !t.err && <div className="text-sm text-muted">Retrieving evidence and generating an answer…</div>}
                  {t.err && <Alert kind="error">{t.err}</Alert>}
                  {t.r && (
                    <div className="max-w-[85%] rounded-2xl rounded-bl-sm border border-line bg-canvas px-4 py-3 text-sm">
                      <p className="whitespace-pre-wrap">{t.r.answer.answer}</p>
                      <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
                        {t.r.answer.citations.map((c: string) => <span key={c} className="rounded-full border border-line bg-white px-2 py-0.5 text-navy">{c}</span>)}
                        <span className="text-muted">confidence {t.r.answer.confidence.toFixed(2)}</span>
                      </div>
                      {t.r.answer.refused && <div className="mt-2 rounded-lg border border-[#ebd7ae] bg-[#fbf4e6] px-3 py-2 text-xs text-[#7a5a1e]">Refused ({t.r.refusal_applied_by}): {t.r.answer.refusal_reason}</div>}
                      {!t.r.contract_valid && <div className="mt-1 text-xs text-muted">Output contract issues: {t.r.contract_errors.join("; ")}</div>}
                      <details className="mt-2 text-xs"><summary className="cursor-pointer text-muted">Citations and evidence ({t.r.retrieved.length})</summary>
                        <div className="mt-2 space-y-2">
                          {t.r.retrieved.map((e: any, j: number) => <div key={j} className="rounded bg-white p-2"><b>{e.source_filename}</b> ({e.location}, similarity {e.score.toFixed(2)})<div className="text-muted">{e.excerpt.slice(0, 300)}</div></div>)}
                          {t.r.tool_results.map((x: any, j: number) => <div key={`t${j}`} className="rounded bg-white p-2"><b>Tool {x.tool}</b>: {x.ok ? JSON.stringify(x.output).slice(0, 300) : x.error}</div>)}
                        </div>
                      </details>
                    </div>
                  )}
                </div>
              ))}
              <div ref={end} />
            </div>
            <form onSubmit={ask} className="flex gap-2 border-t border-line p-3">
              <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask the agent" />
              <button className="btn-primary" disabled={busy || !q.trim()}>Send</button>
            </form>
          </div>
        </>
      )}
    </>
  );
}
