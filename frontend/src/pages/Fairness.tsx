import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useSearchParams } from "react-router-dom";
import { api, CounterfactualGroup, Fairness as FairnessData } from "../api";
import RunPicker from "../components/RunPicker";
import { Card, Empty, ErrorBox, Loading, Notice, PageHeader, Select, Tag } from "../components/ui";
import { AXIS, GRID, SERIES, pct, rampColor, rampText } from "../format";
import { useAsync } from "../hooks";

const HEAT_METRICS = [
  ["accuracy", "Accuracy"], ["refusal_rate", "Refusal"], ["helpfulness", "Helpfulness"], ["hallucination_rate", "Hallucination"],
] as const;

export default function Fairness() {
  const [params, setParams] = useSearchParams();
  const run = params.get("run") ?? "latest";
  const { data, error, loading, reload } = useAsync(() => api.fairness(run), [run]);
  return (
    <div className="space-y-6">
      <PageHeader title="Fairness slices" subtitle="Counterfactual variants that change only a user-segment cue. The correct answer is identical, so any difference is unequal treatment."
        actions={<RunPicker value={run} onChange={(v) => setParams({ run: v })} />} />
      <Notice tone="blue">Segments are synthetic test personas (names, age, language proficiency, tier, region, disability cues) used to probe for unequal treatment. No real customer data is involved.</Notice>
      {loading ? <Loading /> : error ? <ErrorBox message={error} onRetry={reload} /> : !data || data.slices.length === 0 ? (
        <Empty title="No counterfactual items in this run" />
      ) : <FairnessBody data={data} />}
    </div>
  );
}

function FairnessBody({ data }: { data: FairnessData }) {
  const dims = Array.from(new Set(data.slices.map((s) => s.dimension)));
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Max accuracy gap" value={pct(data.max_accuracy_gap)} hint={data.max_accuracy_gap_dimension ?? ""} bad={(data.max_accuracy_gap ?? 0) > data.gap_threshold} />
        <Stat label="Max refusal-rate gap" value={pct(data.max_refusal_gap)} hint={data.max_refusal_gap_dimension ?? ""} bad={(data.max_refusal_gap ?? 0) > data.gap_threshold} />
        <Stat label="Counterfactual consistency" value={pct(data.counterfactual_consistency)} hint={`pairs ${pct(data.pair_consistency)}`} bad={(data.counterfactual_consistency ?? 1) < 0.95} />
      </div>
      {data.flagged.length > 0 ? (
        <Card title="Statistically significant gaps" subtitle={`Gap above ${pct(data.gap_threshold, 0)} with p < 0.05 (two-proportion test) or a bootstrap CI excluding zero.`}>
          <ul className="space-y-1 text-sm text-red-700">{data.flagged.map((f) => <li key={f}>• {f}</li>)}</ul>
        </Card>
      ) : <Notice tone="green">No statistically significant gap above {pct(data.gap_threshold, 0)}.</Notice>}

      <Card title="Gap heatmap" subtitle="Largest difference between slices of each dimension. Darker means a bigger gap; hover a cell for best vs worst slice.">
        <div className="overflow-x-auto">
          <table className="w-full border-separate border-spacing-0.5 text-sm">
            <thead><tr><th className="px-2 py-1 text-left text-xs font-semibold text-slate-500">Dimension</th>
              {HEAT_METRICS.map(([, l]) => <th key={l} className="px-2 py-1 text-xs font-semibold text-slate-500">{l}</th>)}</tr></thead>
            <tbody>{dims.map((dim) => (
              <tr key={dim}><td className="px-2 py-1 font-medium text-slate-700">{dim}</td>
                {HEAT_METRICS.map(([m]) => {
                  const g = data.gaps.find((x) => x.dimension === dim && x.metric === m);
                  if (!g) return <td key={m} className="rounded bg-slate-50 px-2 py-2 text-center text-xs text-slate-400">n/a</td>;
                  const t = Math.min(1, g.gap / 0.5);
                  return <td key={m} title={`${g.best_value} ${pct(g.best)} vs ${g.worst_value} ${pct(g.worst)}${g.p_value !== null ? ` · p=${g.p_value.toFixed(3)}` : ""}`}
                    className="rounded px-2 py-2 text-center font-semibold tabular-nums" style={{ background: rampColor(t), color: rampText(t) }}>
                    {pct(g.gap, 0)}{g.flagged && " ⚑"}</td>;
                })}</tr>
            ))}</tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-slate-500">⚑ = flagged (significant and above threshold). Slices smaller than {data.min_slice_size} items are not compared.</p>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {dims.map((dim) => {
          const rows = data.slices.filter((s) => s.dimension === dim).map((s) => ({
            slice: s.value + (s.below_min_size ? " (small)" : ""), accuracy: s.metrics.accuracy, refusal: s.metrics.refusal_rate, n: s.n }));
          return (
            <Card key={dim} title={dim} subtitle={`${rows.length} slices · n per slice ${rows.map((r) => r.n).join("/")}`}>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={rows} margin={{ top: 4, right: 4, bottom: 0, left: -16 }} barGap={2}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="slice" tick={{ fontSize: 11, fill: AXIS }} tickLine={false} axisLine={{ stroke: GRID }} interval={0} />
                  <YAxis domain={[0, 1]} tickFormatter={(v: number) => pct(v, 0)} tick={{ fontSize: 11, fill: AXIS }} tickLine={false} axisLine={false} />
                  <Tooltip formatter={(v: number, name) => [pct(v), name]} contentStyle={{ fontSize: 12, borderRadius: 8 }} cursor={{ fill: "#f1f5f9" }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} iconType="square" />
                  <Bar dataKey="accuracy" name="Accuracy" fill={SERIES[0]} radius={[4, 4, 0, 0]} isAnimationActive={false} />
                  <Bar dataKey="refusal" name="Refusal rate" fill={SERIES[1]} radius={[4, 4, 0, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          );
        })}
      </div>

      <Card title="Per-slice metrics">
        <div className="overflow-x-auto"><table className="table-base">
          <thead><tr><th>Dimension</th><th>Slice</th><th className="num">n</th><th className="num">Accuracy</th><th className="num">Hallucination</th><th className="num">Refusal</th><th className="num">Helpfulness</th><th className="num">Avg words</th></tr></thead>
          <tbody>{data.slices.map((s) => (
            <tr key={`${s.dimension}-${s.value}`}><td>{s.dimension}</td><td>{s.value} {s.below_min_size && <Tag tone="amber">small</Tag>}</td><td className="num">{s.n}</td>
              <td className="num">{pct(s.metrics.accuracy)}</td><td className="num">{pct(s.metrics.hallucination_rate)}</td><td className="num">{pct(s.metrics.refusal_rate)}</td>
              <td className="num">{pct(s.metrics.helpfulness)}</td><td className="num">{s.metrics.answer_words.toFixed(1)}</td></tr>
          ))}</tbody></table></div>
      </Card>

      <PairViewer groups={data.groups ?? []} />
    </>
  );
}

function PairViewer({ groups }: { groups: CounterfactualGroup[] }) {
  const [onlyInconsistent, setOnlyInconsistent] = useState(true);
  const visible = groups.filter((g) => !onlyInconsistent || !g.consistent);
  const [selected, setSelected] = useState("");
  const group = visible.find((g) => g.group === selected) ?? visible[0];
  return (
    <Card title="Counterfactual pair viewer" subtitle="Same question, one cue changed. Words that differ from the first variant's answer are highlighted."
      actions={<label className="flex items-center gap-2 text-xs text-slate-600"><input type="checkbox" checked={onlyInconsistent}
        onChange={(e) => setOnlyInconsistent(e.target.checked)} /> Inconsistent only</label>}>
      {visible.length === 0 ? <Empty title="All counterfactual groups are consistent" hint="Every variant received the same facts and decision." /> : (
        <>
          <Select label="Group" value={group?.group ?? ""} onChange={setSelected} className="mb-4 max-w-md"
            options={visible.map((g) => ({ value: g.group, label: `${g.group}${g.consistent ? "" : " ⚠"} (${g.variants.length} variants)` }))} />
          {group && (
            <>
              {group.differences.length > 0 && <p className="mb-3 text-sm text-red-700">{group.differences.join("; ")}</p>}
              <div className="grid gap-3 md:grid-cols-2">
                {group.variants.map((v) => (
                  <div key={v.item_id} className={`rounded-lg border p-3 text-sm ${v.correct ? "border-slate-200" : "border-red-200 bg-red-50/40"}`}>
                    <div className="mb-1 flex flex-wrap items-center gap-1"><Tag tone="blue">{v.slice_value}</Tag>
                      {v.correct ? <Tag tone="green">pass</Tag> : <Tag tone="red">fail</Tag>}{v.non_answer && <Tag tone="amber">refused</Tag>}
                      <Tag>decision: {v.decision ?? "–"}</Tag></div>
                    <p className="text-xs italic text-slate-500">{v.question}</p>
                    <DiffText text={v.answer} reference={group.variants[0].answer} />
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}
    </Card>
  );
}

function DiffText({ text, reference }: { text: string; reference: string }) {
  const refWords = useMemo(() => new Set(reference.toLowerCase().split(/\s+/)), [reference]);
  if (text === reference) return <p className="mt-2 text-slate-800">{text}</p>;
  return (
    <p className="mt-2 text-slate-800">{text.split(/(\s+)/).map((w, i) =>
      /\s+/.test(w) || refWords.has(w.toLowerCase()) ? <span key={i}>{w}</span> :
        <mark key={i} className="rounded bg-amber-200 px-0.5">{w}</mark>)}</p>
  );
}

function Stat({ label, value, hint, bad }: { label: string; value: string; hint: string; bad: boolean }) {
  return (
    <div className={`rounded-xl border bg-white p-4 shadow-sm ${bad ? "border-red-200" : "border-slate-200"}`}>
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{value}</p>
      <p className={`text-xs ${bad ? "text-red-700" : "text-slate-500"}`}>{bad ? "⚠ above threshold · " : ""}{hint}</p>
    </div>
  );
}
