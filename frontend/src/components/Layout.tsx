import {
  Database, GitCompare, LayoutDashboard, ListChecks, Menu, Rocket, Scale, Settings, ShieldCheck, SlidersHorizontal, X,
} from "lucide-react";
import { ReactNode, useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { api, Status } from "../api";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/releases", label: "Releases", icon: Rocket },
  { to: "/compare", label: "Compare", icon: GitCompare },
  { to: "/items", label: "Item explorer", icon: ListChecks },
  { to: "/fairness", label: "Fairness", icon: Scale },
  { to: "/golden", label: "Golden set", icon: Database },
  { to: "/gates", label: "Gates", icon: SlidersHorizontal },
  { to: "/settings", label: "Settings", icon: Settings },
];

export default function Layout({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [open, setOpen] = useState(false);
  const location = useLocation();

  useEffect(() => { setOpen(false); }, [location.pathname]);
  useEffect(() => {
    let alive = true;
    const load = () => api.status().then((s) => alive && setStatus(s)).catch(() => alive && setStatus(null));
    load();
    const t = window.setInterval(load, 8000);
    return () => { alive = false; window.clearInterval(t); };
  }, [location.pathname]);

  const sidebar = (
    <nav className="flex h-full flex-col bg-slate-900 text-slate-300">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-green-600 text-white"><ShieldCheck className="h-5 w-5" /></div>
        <div>
          <p className="text-sm font-semibold text-white">GoldenGate</p>
          <p className="text-[11px] text-slate-400">RAG regression suite</p>
        </div>
      </div>
      <ul className="flex-1 space-y-0.5 px-3">
        {NAV.map(({ to, label, icon: Icon }) => (
          <li key={to}>
            <NavLink to={to} end={to === "/"}
              className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${
                isActive ? "bg-green-600/15 font-medium text-green-400" : "hover:bg-slate-800 hover:text-white"}`}>
              <Icon className="h-4 w-4" aria-hidden />{label}
            </NavLink>
          </li>
        ))}
      </ul>
      <div className="space-y-1 border-t border-slate-800 px-5 py-4 text-[11px] text-slate-400">
        <p>Judge: <span className="font-medium text-slate-200">{status?.judge.effective === "llm" ? `LLM (${status.judge.judge_model})` : "offline"}</span></p>
        <p>Baseline: <span className="font-medium text-slate-200">{status?.baseline ?? "none"}</span></p>
        <p>v{status?.version ?? "–"}</p>
      </div>
    </nav>
  );

  return (
    <div className="min-h-screen bg-slate-50">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 lg:block">{sidebar}</aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/50" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64">{sidebar}</aside>
        </div>
      )}
      <div className="lg:pl-60">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-slate-200 bg-white/90 px-4 py-2.5 backdrop-blur lg:hidden">
          <button aria-label={open ? "Close menu" : "Open menu"} onClick={() => setOpen(!open)} className="rounded p-1 text-slate-700">
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
          <span className="font-semibold text-slate-900">GoldenGate</span>
        </header>
        {status?.judge.warning && (
          <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-900 sm:px-8">
            <strong>Offline judge mode.</strong> {status.judge.warning}
          </div>
        )}
        {status?.active_job && (
          <div className="border-b border-blue-200 bg-blue-50 px-4 py-2 text-xs text-blue-900 sm:px-8">
            Running: {status.active_job.label} ({status.active_job.done}/{status.active_job.total || "…"})
          </div>
        )}
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-8 sm:py-8">{children}</main>
      </div>
    </div>
  );
}
