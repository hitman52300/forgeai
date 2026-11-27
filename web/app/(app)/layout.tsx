"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

const NAV: [string, [string, string][]][] = [
  ["Overview", [["/dashboard", "Dashboard"]]],
  ["Build", [["/create", "Create New Agent"], ["/interview", "Interview"], ["/requirements", "Requirements Review"], ["/execution", "Factory Execution"]]],
  ["Quality", [["/evaluation", "Evaluation Dashboard"], ["/studio", "Agent Studio"]]],
  ["Operate", [["/chat", "Agent Chat"], ["/reports", "Reports & Artifacts"]]],
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const [email, setEmail] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const sb = supabase();
    sb.auth.getSession().then(({ data }) => {
      if (!data.session) router.replace("/");
      else setEmail(data.session.user.email ?? "");
    });
    const { data: sub } = sb.auth.onAuthStateChange((_e, s) => { if (!s) router.replace("/"); });
    return () => sub.subscription.unsubscribe();
  }, [router]);

  if (email === null) return null; // auth gate: nothing renders before the session is confirmed

  return (
    <div className="flex min-h-screen">
      <aside className={`fixed inset-y-0 left-0 z-30 w-64 border-r border-line bg-surface px-4 py-5 transition-transform md:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}>
        <Link href="/dashboard" className="mb-7 flex items-center gap-2.5 px-2">
          <img src="/mark.svg" alt="" className="h-8 w-8" />
          <div>
            <div className="font-bold leading-tight text-navy">ForgeAI</div>
            <div className="text-[11px] text-muted">Agent engineering factory</div>
          </div>
        </Link>
        <nav className="space-y-5">
          {NAV.map(([group, items]) => (
            <div key={group}>
              <div className="mb-1.5 px-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">{group}</div>
              {items.map(([href, label]) => (
                <Link key={href} href={href} onClick={() => setOpen(false)}
                  className={`block rounded-lg px-2.5 py-1.5 text-sm transition ${path === href ? "bg-accent-soft font-semibold text-navy" : "text-ink hover:bg-canvas"}`}>
                  {label}
                </Link>
              ))}
            </div>
          ))}
        </nav>
        <div className="absolute inset-x-4 bottom-5">
          <div className="mb-2 truncate rounded-lg border border-line bg-canvas px-3 py-2 text-xs text-muted">
            Signed in as<br /><span className="font-semibold text-ink">{email}</span>
          </div>
          <button className="btn w-full" onClick={async () => { await supabase().auth.signOut(); router.replace("/"); }}>Sign out</button>
        </div>
      </aside>
      <div className="flex-1 md:pl-64">
        <div className="sticky top-0 z-20 flex items-center border-b border-line bg-surface/90 px-4 py-3 backdrop-blur md:hidden">
          <button className="btn px-3 py-1.5" onClick={() => setOpen(!open)}>Menu</button>
          <span className="ml-3 font-bold text-navy">ForgeAI</span>
        </div>
        <main className="mx-auto max-w-6xl px-5 py-8 md:px-10 md:py-10">{children}</main>
      </div>
    </div>
  );
}
