import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, MetricDelta } from "../api";
import { Card, Empty, ErrorBox, Loading, Notice, PageHeader, Select, StatusPill, Tag, VerdictBadge } from "../components/ui";
import { fmtDelta, fmtMetric, pct } from "../format";
import { useAsync } from "../hooks";

export default function Compare() {
  const [params, setParams] = useSearchParams();
  const releases = useAsync(() => api.releases(), []);
  const baselineDefault = releases.data?.find((r) => r.is_baseline)?.release_id ?? "baseline";
  const [baseline, setBaseline] = useState(params.get("baseline") ?? "");
  const [showAll, setShowAll] = useState(false);
  const current = params.get("current") ?? "latest";
  const base = baseline || baselineDefault;
  const cmp = useAsync(() => api.compare(base, current), [base, current]);
  const options = (releases.data ?? []).map((r) => ({ value: r.release_id, label: r.release_id + (r.is_baseline ? " (baseline)" : "") }));

  return (
    <div className="space-y-6">
      <PageHeader title="Compare releases" subtitle="Metric deltas with paired-bootstrap 95% confidence intervals. Newly failing items first."
        actions={<>
          <Select label="Baseline" value={base} onChange={(v) => setBaseline(v)} options={[{ value: "baseline", label: "Current baseline" }, ...options]} />
          <Select label="Current" value={current} onChange={(v) => setParams({ current: v })} options={[{ value: "latest", label: "Latest run" }, ...options]} />
        </>} />
      {cmp.loading ? <Loading label="Comparing…" /> : cmp.error ? <ErrorBox message={cmp.error} onRetry={cmp.reload} /> : !cmp.data ? null : (
        <>
          <Card>
            <div className="flex flex-wrap items-center gap-4">
              <VerdictBadge verdict={cmp.data.gates.verdict} size="lg" />
              <p className="text-sm text-slate-600"><strong>{cmp.data.current_release}</strong> (golden {cmp.data.current_golden}) vs
                baseline <strong>{cmp.data.baseline_release}</strong> (golden {cmp.data.baseline_golden}) · {cmp.data.common_items} shared items ·{" "}
                <span className="text-red-700">{cmp.data.newly_failing.length} newly failing</span> ·{" "}
                <span className="text-green-700">{cmp.data.newly_passing.length} newly passing</span></p>
            </div>
            {cmp.data.warnings.map((w) => <div className="mt-3" key={w}><Notice>{w}</Notice></div>)}
          </Card>

          <Card title="Metric deltas" subtitle="Bars show the 95% CI of the delta; a regression is a worse delta whose interval excludes zero.">
            <div className="overflow-x-auto">
              <table className="table-base">
                <thead><tr><th>Metric</th><th className="num">Baseline</th><th className="num">Current</th><th className="num">Δ</th><th>95% CI of Δ</th><th></th></tr></thead>
                <tbody>{cmp.data.metrics.map((d) => <DeltaRow key={d.name} d={d} />)}</tbody>
              </table>
            </div>
          </Card>

          <Card title={`Newly failing items (${cmp.data.newly_failing.length})`} subtitle="Items that passed in the baseline and fail now; critical items first.">
            {cmp.data.newly_failing.length === 0 ? <Empty title="No regressions" hint="Every item that passed in the baseline still passes." /> : (
              <div className="space-y-3">
                {cmp.data.newly_failing.slice(0, showAll ? undefined : 10).map((c) => (
                  <details key={c.item_id} className="rounded-lg border border-slate-200 p-3">
                    <summary className="flex cursor-pointer flex-wrap items-center gap-2 text-sm">
                      <code className="text-xs">{c.item_id}</code>{c.critical && <Tag tone="red">critical</Tag>}
                      <span className="text-slate-700">{c.question}</span>
                    </summary>
                    <p className="mt-2 text-xs text-red-700">{c.reasons.join("; ")}</p>
                    <div className="mt-2 grid gap-3 text-sm md:grid-cols-2">
                      <div className="rounded-lg bg-slate-50 p-2"><p className="text-xs font-semibold text-slate-500">Baseline answer</p>{c.baseline_answer}</div>
                      <div className="rounded-lg bg-red-50 p-2"><p className="text-xs font-semibold text-red-600">Current answer</p>{c.current_answer}</div>
                    </div>
                    <Link className="mt-2 inline-block text-xs text-green-700 underline" to={`/items?run=${cmp.data!.current_run_id}&item=${c.item_id}`}>Open in item explorer</Link>
                  </details>
                ))}
                {cmp.data.newly_failing.length > 10 && (
                  <button className="btn-secondary" onClick={() => setShowAll(!showAll)}>
                    {showAll ? "Show fewer" : `Show all ${cmp.data.newly_failing.length}`}</button>
                )}
              </div>
            )}
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="Gate results">
              <ul className="space-y-2">{cmp.data.gates.gates.map((g) => (
                <li key={g.id} className="flex items-start gap-3 text-sm"><StatusPill status={g.status} /><div><code className="text-xs">{g.id}</code><p className="text-slate-600">{g.message}</p></div></li>
              ))}</ul>
            </Card>
            <Card title="Largest per-slice changes" subtitle="Counterfactual items only.">
              {cmp.data.slice_changes.length === 0 ? <Empty title="No shared slices" /> : (
                <table className="table-base"><thead><tr><th>Slice</th><th>Metric</th><th className="num">Baseline</th><th className="num">Current</th><th className="num">Δ</th></tr></thead>
                  <tbody>{cmp.data.slice_changes.slice(0, 12).map((s) => (
                    <tr key={`${s.dimension}-${s.value}-${s.metric}`}><td>{s.dimension}: {s.value}</td><td>{s.metric}</td>
                      <td className="num">{pct(s.baseline)}</td><td className="num">{pct(s.current)}</td>
                      <td className={`num font-medium ${Math.abs(s.delta) < 0.0001 ? "" : (s.metric === "refusal_rate" ? s.delta > 0 : s.delta < 0) ? "text-red-700" : "text-green-700"}`}>{fmtDelta(s.metric, s.delta)}</td></tr>
                  ))}</tbody></table>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function DeltaRow({ d }: { d: MetricDelta }) {
  const worse = d.delta !== null && (d.higher_is_better ? d.delta < 0 : d.delta > 0);
  const color = d.regression ? "text-red-700" : d.delta && !worse && d.significant ? "text-green-700" : "text-slate-700";
  const scale = 0.5; // +/- 50 points spans the bar
  const pos = (v: number) => `${Math.max(0, Math.min(100, 50 + (v / scale) * 50))}%`;
  const isRate = d.kind === "rate";
  return (
    <tr>
      <td>{d.label}</td><td className="num">{fmtMetric(d.name, d.baseline)}</td><td className="num">{fmtMetric(d.name, d.current)}</td>
      <td className={`num font-semibold ${color}`}>{fmtDelta(d.name, d.delta)}</td>
      <td className="min-w-[10rem]">
        {isRate && d.delta_ci_low !== null && d.delta_ci_high !== null ? (
          <div className="relative h-4" title={`${fmtDelta(d.name, d.delta_ci_low)} … ${fmtDelta(d.name, d.delta_ci_high)}`}>
            <div className="absolute left-1/2 top-0 h-4 w-px bg-slate-300" />
            <div className={`absolute top-1.5 h-1 rounded ${d.regression ? "bg-red-500" : "bg-blue-500"}`}
              style={{ left: pos(d.delta_ci_low), width: `calc(${pos(d.delta_ci_high)} - ${pos(d.delta_ci_low)} + 2px)` }} />
            {d.delta !== null && <div className="absolute top-0.5 h-3 w-1 rounded bg-slate-800" style={{ left: pos(d.delta) }} />}
          </div>
        ) : <span className="text-xs text-slate-400">–</span>}
      </td>
      <td>{d.regression && <Tag tone="red">regression</Tag>}</td>
    </tr>
  );
}
