import { FileText } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api";
import TrendChart from "../components/TrendChart";
import { Card, Empty, ErrorBox, Loading, Notice, PageHeader, StatusPill, VerdictBadge } from "../components/ui";
import { fmtDate, fmtDelta, fmtMetric, pct } from "../format";
import { useAsync } from "../hooks";

const TRENDS = [
  ["accuracy", "Accuracy"], ["hallucination_rate", "Hallucination rate"], ["citation_precision", "Citation precision"],
  ["citation_recall", "Citation recall"], ["max_slice_gap", "Max fairness gap"], ["counterfactual_consistency", "Counterfactual consistency"],
] as const;

export default function Overview() {
  const { data, error, loading, reload } = useAsync(() => api.overview(), []);
  if (loading) return <Loading label="Loading overview…" />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data || !data.current) {
    return <Empty title="No runs yet" hint="Seed the demo from Settings → Reset demo data, or run `goldengate demo`."
      action={<Link to="/settings" className="btn-primary mt-2">Open settings</Link>} />;
  }
  const { current, history, thresholds } = data;
  const meta = current.meta;
  const gates = current.gates;
  return (
    <div className="space-y-6">
      <PageHeader title="Overview" subtitle="Current release verdict, gate status and release-over-release trends."
        actions={<a className="btn-secondary" href={api.reportUrl(meta.run_id, "html")} target="_blank" rel="noreferrer">
          <FileText className="h-4 w-4" /> HTML report</a>} />

      <Card>
        <div className="flex flex-wrap items-center gap-6">
          <VerdictBadge verdict={gates?.verdict} size="lg" />
          <div className="min-w-0 flex-1">
            <p className="text-lg font-semibold text-slate-900">{meta.release.release_id}
              <span className="ml-2 text-sm font-normal text-slate-500">{meta.release.description}</span></p>
            <p className="mt-1 text-sm text-slate-500">
              Run <code className="text-xs">{meta.run_id}</code> · golden {meta.golden_version} · model {meta.release.model} ·
              judge {Object.keys(meta.judges_used).join(", ")} · baseline {data.baseline ?? "none"} · {fmtDate(meta.finished_at)}
            </p>
          </div>
          <div className="grid grid-cols-3 gap-6 text-center">
            <Kpi label="Accuracy" value={pct(current.metrics.accuracy?.value)} />
            <Kpi label="Hallucination" value={pct(current.metrics.hallucination_rate?.value)} />
            <Kpi label="Max slice gap" value={pct(current.metrics.max_slice_gap?.value)} />
          </div>
        </div>
        {gates && gates.reasons.length > 0 && (
          <ul className="mt-4 space-y-1 text-sm text-red-700">{gates.reasons.map((r) => <li key={r}>• {r}</li>)}</ul>
        )}
        {[...(gates?.warnings ?? []), ...meta.warnings].map((w) => <div key={w} className="mt-3"><Notice>{w}</Notice></div>)}
      </Card>

      {gates && (
        <div>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Gate status</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {gates.gates.map((g) => (
              <div key={g.id} className={`rounded-xl border bg-white p-4 shadow-sm ${g.status === "FAIL" ? "border-red-200" : "border-slate-200"}`}>
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-sm font-medium text-slate-900" title={g.id}>{g.metric_label}</p>
                  <StatusPill status={g.status} />
                </div>
                <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">
                  {g.kind === "critical_items" ? `${g.current ?? 0} failing`
                    : g.kind === "max_drop" || g.kind === "max_increase"
                      ? (g.delta === null ? "–" : <>{fmtDelta(g.metric ?? "", g.delta)}<span className="ml-1 text-xs font-normal text-slate-500">vs baseline</span></>)
                      : fmtMetric(g.metric ?? "", g.current)}
                </p>
                <p className="mt-1 text-xs text-slate-500">{g.description}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Trends across releases</h2>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {TRENDS.map(([metric, label]) => (
            <TrendChart key={metric} history={history} metric={metric} label={label}
              threshold={thresholds[metric]?.threshold} kind={thresholds[metric]?.kind} />
          ))}
        </div>
        <p className="mt-2 text-xs text-slate-500">Each point is the latest run of a release. Dashed red lines are gate thresholds.</p>
      </div>
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return <div><p className="text-2xl font-semibold tabular-nums text-slate-900">{value}</p><p className="text-xs text-slate-500">{label}</p></div>;
}
