import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { HistoryRow } from "../api";
import { AXIS, GRID, SERIES, STATUS, pct, shortRelease } from "../format";

/** One metric across releases (single series) with its gate threshold as a dashed line. */
export default function TrendChart({ history, metric, label, threshold, kind }: {
  history: HistoryRow[]; metric: string; label: string; threshold?: number; kind?: string;
}) {
  const data = history.map((h) => ({ release: shortRelease(h.release_id), value: h.metrics[metric] ?? null, verdict: h.verdict }));
  const values = data.map((d) => d.value).filter((v): v is number => v !== null);
  const all = threshold !== undefined ? [...values, threshold] : values;
  const lo = Math.max(0, Math.floor((Math.min(...all) - 0.02) * 10) / 10);
  const hi = Math.min(1, Math.ceil((Math.max(...all) + 0.02) * 10) / 10);
  const step = hi - lo > 0.5 ? 0.2 : 0.1;
  const ticks: number[] = [];
  for (let t = lo; t <= hi + 1e-9; t += step) ticks.push(Math.round(t * 100) / 100);
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-slate-900">{label}</h3>
        {threshold !== undefined && (
          <span className="text-[11px] text-slate-500">gate {kind === "min" ? "≥" : "≤"} {pct(threshold, 0)}</span>
        )}
      </div>
      {values.length === 0 ? <p className="py-10 text-center text-sm text-slate-400">No data yet</p> : (
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis dataKey="release" tick={{ fontSize: 11, fill: AXIS }} tickLine={false} axisLine={{ stroke: GRID }} />
            <YAxis domain={[lo, hi]} ticks={ticks} tickFormatter={(v: number) => pct(v, 0)} tick={{ fontSize: 11, fill: AXIS }}
              tickLine={false} axisLine={false} width={46} />
            <Tooltip formatter={(v: number) => [pct(v), label]} labelFormatter={(l) => `Release ${l}`}
              contentStyle={{ fontSize: 12, borderRadius: 8, borderColor: GRID }} />
            {threshold !== undefined && (
              <ReferenceLine y={threshold} stroke={STATUS.critical} strokeDasharray="5 4" strokeWidth={1.5}
                label={{ value: "gate", position: "insideTopRight", fill: STATUS.critical, fontSize: 10 }} />
            )}
            <Line type="linear" dataKey="value" stroke={SERIES[0]} strokeWidth={2} isAnimationActive={false}
              dot={{ r: 4, fill: SERIES[0], stroke: "#fff", strokeWidth: 2 }} activeDot={{ r: 6 }} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
