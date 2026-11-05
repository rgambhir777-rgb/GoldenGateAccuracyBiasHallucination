// Formatting helpers and the validated chart palette.

const VALUE_METRICS = new Set(["avg_answer_words", "avg_latency_ms", "avg_total_tokens"]);

export const pct = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? "–" : `${(v * 100).toFixed(digits)}%`;

export const fmtMetric = (name: string, v: number | null | undefined) =>
  v === null || v === undefined ? "–" : VALUE_METRICS.has(name) ? v.toFixed(1) : pct(v);

export const fmtDelta = (name: string, v: number | null | undefined) => {
  if (v === null || v === undefined) return "–";
  if (VALUE_METRICS.has(name)) return `${v >= 0 ? "+" : ""}${v.toFixed(1)}`;
  return `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)} pts`;
};

export const shortRelease = (id: string) => id.replace("release_", "");

export const fmtDate = (iso: string | null | undefined) => {
  if (!iso) return "–";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
};

// Chart colors: categorical slots validated for CVD separation and contrast (dataviz reference palette),
// status colors reserved for pass/fail and threshold lines.
export const SERIES = ["#2a78d6", "#eb6834"];
export const STATUS = { good: "#0ca30c", critical: "#d03b3b" };
export const GRID = "#e5e7eb";
export const AXIS = "#6b7280";

// Sequential blue ramp (light -> dark) for the gap heatmap.
const RAMP = ["#f8fafc", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];
export const rampColor = (t: number) => RAMP[Math.max(0, Math.min(RAMP.length - 1, Math.round(t * (RAMP.length - 1))))];
export const rampText = (t: number) => (t > 0.5 ? "#ffffff" : "#0f172a");
