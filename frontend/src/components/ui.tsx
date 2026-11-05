import { AlertTriangle, CheckCircle2, Inbox, Loader2, MinusCircle, RefreshCw, XCircle } from "lucide-react";
import { ReactNode } from "react";
import { GateStatus, Verdict } from "../api";

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Card({ title, subtitle, children, actions, className = "" }:
  { title?: ReactNode; subtitle?: ReactNode; children: ReactNode; actions?: ReactNode; className?: string }) {
  return (
    <section className={`rounded-xl border border-slate-200 bg-white p-5 shadow-sm ${className}`}>
      {(title || actions) && (
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            {title && <h2 className="text-base font-semibold text-slate-900">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function VerdictBadge({ verdict, size = "md" }: { verdict: Verdict | null | undefined; size?: "sm" | "md" | "lg" }) {
  if (!verdict) return <span className="text-xs text-slate-400">not gated</span>;
  const ship = verdict === "SHIP";
  const sizes = { sm: "px-2 py-0.5 text-xs", md: "px-3 py-1 text-sm", lg: "px-5 py-2 text-2xl" };
  const Icon = ship ? CheckCircle2 : XCircle;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-lg font-bold tracking-wide ${sizes[size]} ${
      ship ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
      <Icon className={size === "lg" ? "h-6 w-6" : "h-4 w-4"} aria-hidden />
      {verdict}
    </span>
  );
}

export function StatusPill({ status }: { status: GateStatus }) {
  const styles = {
    PASS: ["bg-green-100 text-green-700", CheckCircle2],
    FAIL: ["bg-red-100 text-red-700", XCircle],
    SKIP: ["bg-slate-100 text-slate-500", MinusCircle],
  } as const;
  const [cls, Icon] = styles[status];
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${cls}`}>
      <Icon className="h-3.5 w-3.5" aria-hidden />{status}
    </span>
  );
}

export function Tag({ children, tone = "slate" }: { children: ReactNode; tone?: "slate" | "green" | "red" | "amber" | "blue" }) {
  const tones = {
    slate: "bg-slate-100 text-slate-600", green: "bg-green-100 text-green-700", red: "bg-red-100 text-red-700",
    amber: "bg-amber-100 text-amber-800", blue: "bg-blue-100 text-blue-700",
  };
  return <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium ${tones[tone]}`}>{children}</span>;
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-slate-500" role="status">
      <Loader2 className="h-5 w-5 animate-spin text-green-600" aria-hidden /> {label}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800" role="alert">
      <AlertTriangle className="mt-0.5 h-5 w-5 flex-none" aria-hidden />
      <div className="flex-1">
        <p className="font-medium">Something went wrong</p>
        <p className="mt-0.5">{message}</p>
      </div>
      {onRetry && (
        <button onClick={onRetry} className="btn-secondary !py-1 text-xs"><RefreshCw className="h-3.5 w-3.5" /> Retry</button>
      )}
    </div>
  );
}

export function Empty({ title, hint, action }: { title: string; hint?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-14 text-center">
      <Inbox className="h-8 w-8 text-slate-300" aria-hidden />
      <p className="font-medium text-slate-700">{title}</p>
      {hint && <p className="max-w-md text-sm text-slate-500">{hint}</p>}
      {action}
    </div>
  );
}

export function Notice({ tone = "amber", children }: { tone?: "amber" | "blue" | "green" | "red"; children: ReactNode }) {
  const tones = {
    amber: "border-amber-200 bg-amber-50 text-amber-900", blue: "border-blue-200 bg-blue-50 text-blue-900",
    green: "border-green-200 bg-green-50 text-green-900", red: "border-red-200 bg-red-50 text-red-900",
  };
  return <div className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-sm ${tones[tone]}`}>
    <AlertTriangle className="mt-0.5 h-4 w-4 flex-none" aria-hidden /><div>{children}</div></div>;
}

export function Select({ label, value, onChange, options, className = "" }: {
  label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; className?: string;
}) {
  return (
    <label className={`flex flex-col gap-1 text-xs font-medium text-slate-600 ${className}`}>
      {label}
      <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  );
}

export function ProgressBar({ done, total, label }: { done: number; total: number; label?: string }) {
  const p = total > 0 ? Math.round((done / total) * 100) : 0;
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-slate-600"><span className="truncate">{label}</span><span>{total ? `${done}/${total}` : "starting…"}</span></div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-100">
        <div className="h-full rounded-full bg-green-600 transition-all" style={{ width: `${total ? p : 5}%` }} />
      </div>
    </div>
  );
}
