"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

const STEPS = [
  ["Scope", "Interview, groundability matrix and requirements for human approval"],
  ["Build", "Versioned agent definition, retrieval configuration and only the tools it needs"],
  ["Prove", "Verified test set, measured scorecards, targeted fixes and an honest report"],
];

export default function Login() {
  const router = useRouter();
  const [tab, setTab] = useState<"in" | "up">("in");
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "error" | "ok"; text: string } | null>(null);

  useEffect(() => {
    supabase().auth.getSession().then(({ data }) => { if (data.session) router.replace("/dashboard"); });
  }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    if (!email || !pw) return setMsg({ kind: "error", text: "Enter your e-mail and password." });
    if (tab === "up" && pw.length < 8) return setMsg({ kind: "error", text: "Use a password of at least 8 characters." });
    if (tab === "up" && pw !== pw2) return setMsg({ kind: "error", text: "The passwords do not match." });
    setBusy(true);
    try {
      if (tab === "in") {
        const { error } = await supabase().auth.signInWithPassword({ email: email.trim(), password: pw });
        if (error) throw error;
        router.replace("/dashboard");
      } else {
        const { data, error } = await supabase().auth.signUp({ email: email.trim(), password: pw });
        if (error) throw error;
        if (data.session) router.replace("/dashboard");
        else setMsg({ kind: "ok", text: "Account created. Confirm the e-mail sent to you, then sign in." });
      }
    } catch (err: any) {
      setMsg({ kind: "error", text: err?.message || "Authentication failed." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-6 py-10">
      <div className="grid w-full max-w-5xl overflow-hidden rounded-2xl border border-line bg-surface shadow-[0_10px_40px_rgba(20,33,61,0.08)] md:grid-cols-[1.1fr_1fr]">
        <div className="relative overflow-hidden bg-navy p-10 text-[#e8ecf2]">
          <div className="pointer-events-none absolute -bottom-24 -right-24 h-72 w-72 rounded-full border border-white/10" />
          <div className="pointer-events-none absolute -bottom-10 -right-10 h-40 w-40 rounded-full border border-white/10" />
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent text-sm font-bold text-white">F</div>
            <div>
              <div className="font-bold text-white">ForgeAI</div>
              <div className="text-xs text-[#9aa6b8]">The agent that builds agents</div>
            </div>
          </div>
          <h1 className="mt-10 text-[28px] font-bold leading-tight tracking-tight text-white">
            Engineer document-grounded AI agents, with the evidence to trust them.
          </h1>
          <p className="mt-4 text-sm leading-relaxed text-[#b9c2d0]">
            Describe the agent in one paragraph and upload its documents. ForgeAI scopes it, checks what the documents
            can support, and builds, tests and improves it after your approval.
          </p>
          <div className="mt-8 space-y-5">
            {STEPS.map(([t, d], i) => (
              <div key={t} className="flex gap-3">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-white/25 text-xs text-white">{i + 1}</div>
                <div>
                  <div className="text-sm font-semibold text-white">{t}</div>
                  <div className="text-[13px] text-[#9aa6b8]">{d}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="p-10">
          <h2 className="text-2xl font-bold text-navy">{tab === "in" ? "Welcome back" : "Create your account"}</h2>
          <p className="mt-1 text-sm text-muted">
            {tab === "in" ? "Sign in to your ForgeAI workspace." : "Start engineering agents in a few minutes."}
          </p>
          <div className="mt-6 grid grid-cols-2 rounded-lg border border-line bg-canvas p-1 text-sm font-medium">
            {(["in", "up"] as const).map((t) => (
              <button key={t} type="button" onClick={() => { setTab(t); setMsg(null); }}
                className={`rounded-md py-2 transition ${tab === t ? "bg-white text-navy shadow-sm" : "text-muted hover:text-navy"}`}>
                {t === "in" ? "Sign in" : "Create account"}
              </button>
            ))}
          </div>
          <form onSubmit={submit} className="mt-6 space-y-4">
            <div>
              <label className="label">Work e-mail</label>
              <input className="input" type="email" autoComplete="email" placeholder="name@company.com"
                value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div>
              <label className="label">Password</label>
              <input className="input" type="password" autoComplete={tab === "in" ? "current-password" : "new-password"}
                value={pw} onChange={(e) => setPw(e.target.value)} />
            </div>
            {tab === "up" && (
              <div>
                <label className="label">Confirm password</label>
                <input className="input" type="password" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} />
              </div>
            )}
            {msg && (
              <div className={`rounded-lg border px-3 py-2 text-sm ${msg.kind === "error" ? "border-[#e6c7c7] bg-[#f9ecec] text-[#7a2e2e]" : "border-[#c4dad5] bg-[#e8f1ef] text-[#1f5450]"}`}>
                {msg.text}
              </div>
            )}
            <button className="btn-primary w-full py-2.5" disabled={busy}>
              {busy ? "Please wait…" : tab === "in" ? "Sign in" : "Create account"}
            </button>
          </form>
          <p className="mt-6 text-xs text-muted">Authentication by Supabase Auth. Each account only sees its own projects, runs and agents.</p>
        </div>
      </div>
    </main>
  );
}
