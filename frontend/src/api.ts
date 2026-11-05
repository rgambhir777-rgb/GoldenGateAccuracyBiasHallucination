// Typed client for the GoldenGate FastAPI backend.

export type Verdict = "SHIP" | "BLOCKED";
export type GateStatus = "PASS" | "FAIL" | "SKIP";

export interface MetricValue { name: string; value: number | null; ci_low: number | null; ci_high: number | null; n: number }
export interface MetricInfo { name: string; label: string; higher_is_better: boolean; kind: string; group: string; formula: string }

export interface GateResult {
  id: string; description: string; metric: string | null; metric_label: string; kind: string;
  threshold: number | null; status: GateStatus; current: number | null; baseline: number | null;
  delta: number | null; ci_low: number | null; ci_high: number | null; message: string; failing_items: string[];
}
export interface GateReport { verdict: Verdict; baseline_run_id: string | null; gates: GateResult[]; reasons: string[]; warnings: string[] }

export interface ReleaseInfo {
  release_id: string; version: string; description: string; system: string; model: string;
  prompt_hash: string; retriever_config: Record<string, unknown>; released_at: string | null;
}
export interface RunMeta {
  run_id: string; release: ReleaseInfo; golden_version: string; golden_hash: string; git_commit: string;
  judge_mode: string; judges_used: Record<string, number>; started_at: string; finished_at: string | null;
  n_items: number; warnings: string[];
}
export interface SliceStat { dimension: string; value: string; n: number; metrics: Record<string, number>; below_min_size: boolean }
export interface GapResult {
  dimension: string; metric: string; best_value: string; worst_value: string; best: number; worst: number;
  gap: number; ci_low: number; ci_high: number; p_value: number | null; significant: boolean; flagged: boolean;
}
export interface CounterfactualVariant {
  item_id: string; slice_value: string; question: string; answer: string; correct: boolean;
  decision: string | null; facts_present: string[]; non_answer: boolean;
}
export interface CounterfactualGroup { group: string; dimension: string; consistent: boolean; variants: CounterfactualVariant[]; differences: string[] }
export interface Fairness {
  min_slice_size: number; gap_threshold: number; slices: SliceStat[]; gaps: GapResult[];
  max_accuracy_gap: number | null; max_accuracy_gap_dimension: string | null; max_refusal_gap: number | null;
  max_refusal_gap_dimension: string | null; counterfactual_consistency: number | null; pair_consistency: number | null;
  groups?: CounterfactualGroup[]; flagged: string[];
}
export interface RunPayload {
  meta: RunMeta; metrics: Record<string, MetricValue>; gates: GateReport | null; fairness: Fairness;
  summary: { items: number; failing: number; critical_failing: number };
}
export interface HistoryRow {
  release_id: string; version: string; description: string; model: string; prompt_hash: string; system: string;
  retriever_config: Record<string, unknown>; released_at: string | null; is_baseline: boolean; latest_run_id: string;
  golden_version: string; verdict: Verdict | null; judge_mode: string; run_count: number; finished_at: string | null;
  metrics: Record<string, number | null>; runs?: RunSummary[];
}
export interface RunSummary {
  run_id: string; release_id: string; golden_version: string; judge_mode: string; judges_used: Record<string, number>;
  started_at: string; finished_at: string | null; n_items: number; verdict: Verdict | null; git_commit: string;
  metrics: Record<string, number | null>;
}
export interface Overview {
  current: RunPayload | null; history: HistoryRow[]; baseline: string | null; metrics: MetricInfo[];
  thresholds: Record<string, { threshold: number; kind: string }>;
}
export interface Status {
  version: string; baseline: string | null; has_data: boolean; golden_versions: string[];
  judge: { mode: string; effective: string; provider: string | null; judge_model: string; warning: string | null };
  active_job: Job | null;
}
export interface Job {
  id: string; kind: string; label: string; status: "queued" | "running" | "done" | "error"; done: number; total: number;
  message: string; run_id: string | null; error: string | null;
}
export interface ItemSummary {
  item_id: string; question: string; category: string; difficulty: string; answerable: boolean; critical: boolean;
  slices: Record<string, string>; counterfactual_group: string | null; correct: boolean; hallucinated: boolean;
  key_fact_coverage: number; n_claims: number; n_bad_claims: number; n_citations: number; failure_reasons: string[];
  judge: string; answer_preview: string;
}
export interface ItemList { run_id: string; total: number; count: number; facets: { categories: string[]; slices: string[] }; items: ItemSummary[] }
export interface Claim { text: string; label: "supported" | "contradicted" | "unsupported"; supporting_chunk_ids: string[]; cited_chunk_ids: string[]; evidence: string | null; score: number }
export interface ItemResult extends ItemSummary {
  reference_answer: string; key_facts: string[]; gold_chunk_ids: string[]; expected_decision: string | null;
  response: { answer: string; citations: string[]; retrieved: { chunk_id: string; text: string; score: number; rank: number }[]; latency_ms: number; error: string | null; usage: { prompt_tokens: number; completion_tokens: number } };
  judgment: { judge: string; key_facts: { fact: string; present: boolean; score: number }[]; semantic_match: number; abstained: boolean; refused: boolean; claims: Claim[]; forbidden_hits: string[]; decision: string | null; notes: string[] };
  recall_at_k: number | null; reciprocal_rank: number | null; answer_words: number; n_fabricated_citations: number;
}
export interface ItemDetail {
  item: ItemResult;
  citations: { chunk_id: string; exists: boolean; gold: boolean; text: string | null; supports: boolean }[];
  gold_chunks: { chunk_id: string; text: string | null }[];
  retrieved: { chunk_id: string; text: string; score: number; rank: number; gold: boolean }[];
}
export interface MetricDelta {
  name: string; label: string; group: string; kind: string; higher_is_better: boolean; baseline: number | null;
  current: number | null; delta: number | null; delta_ci_low: number | null; delta_ci_high: number | null;
  significant: boolean; regression: boolean;
}
export interface ItemChange {
  item_id: string; question: string; category: string; critical: boolean; slices: Record<string, string>;
  baseline_correct: boolean; current_correct: boolean; reasons: string[]; baseline_answer: string; current_answer: string;
}
export interface Comparison {
  baseline_run_id: string; current_run_id: string; baseline_release: string; current_release: string;
  baseline_golden: string; current_golden: string; common_items: number; warnings: string[]; metrics: MetricDelta[];
  newly_failing: ItemChange[]; newly_passing: ItemChange[];
  slice_changes: { dimension: string; value: string; metric: string; baseline: number; current: number; delta: number }[];
  gates: GateReport;
}
export interface GoldenItem {
  id: string; question: string; reference_answer: string; key_facts: string[]; forbidden_claims: string[];
  gold_chunk_ids: string[]; category: string; difficulty: string; answerable: boolean; tags: string[];
  slices: Record<string, string>; counterfactual_group: string | null; expected_decision: string | null;
}
export interface GoldenVersion {
  version: string; created: string; description: string; changelog: string[]; item_count: number; content_hash: string;
  frozen: boolean; parent: string | null; valid: boolean; errors: string[]; warnings: string[];
}
export interface GoldenDiff {
  a: string; b: string; added: string[]; removed: string[]; changed: Record<string, string[]>;
  details: Record<string, Record<string, { before: unknown; after: unknown }>>; unchanged: number;
}
export interface GateSpec { id: string; description: string; metric: string | null; kind: string; threshold: number; enabled: boolean }
export interface GateConfig { version: number; min_slice_size: number; gates: GateSpec[] }
export interface SettingsPayload {
  keys: Record<string, string | null>; values: Record<string, string>; env_file: string;
  judge: Status["judge"];
}
export interface SystemOption { id: string; label: string; description: string; available: boolean; reason?: string | null }

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  } catch {
    throw new ApiError("Cannot reach the GoldenGate server. Is it running?", 0);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      detail = (await res.text().catch(() => detail)) || detail;
    }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

const q = (params: Record<string, string | number | boolean | undefined | null>) => {
  const s = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") s.set(k, String(v)); });
  const text = s.toString();
  return text ? `?${text}` : "";
};

export const api = {
  status: () => request<Status>("/api/status"),
  overview: () => request<Overview>("/api/overview"),
  releases: () => request<HistoryRow[]>("/api/releases"),
  runs: () => request<RunSummary[]>("/api/runs"),
  run: (id: string) => request<RunPayload>(`/api/runs/${encodeURIComponent(id)}`),
  items: (id: string, params: Record<string, string | boolean | undefined>) =>
    request<ItemList>(`/api/runs/${encodeURIComponent(id)}/items${q(params)}`),
  item: (runId: string, itemId: string) =>
    request<ItemDetail>(`/api/runs/${encodeURIComponent(runId)}/items/${encodeURIComponent(itemId)}`),
  fairness: (id: string) => request<Fairness>(`/api/runs/${encodeURIComponent(id)}/fairness`),
  compare: (baseline: string, current: string) => request<Comparison>(`/api/compare${q({ baseline, current })}`),
  systems: () => request<SystemOption[]>("/api/systems"),
  startRun: (body: { system: string; golden: string; judge?: string; release?: string }) =>
    request<Job>("/api/runs", { method: "POST", body: JSON.stringify(body) }),
  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  resetDemo: () => request<Job>("/api/demo/reset", { method: "POST" }),
  setBaseline: (release: string) => request<{ release: string }>("/api/baseline", { method: "PUT", body: JSON.stringify({ release }) }),
  golden: () => request<GoldenVersion[]>("/api/golden"),
  goldenItems: (version: string, params: Record<string, string | undefined>) =>
    request<{ version: string; count: number; items: GoldenItem[] }>(`/api/golden/${version}/items${q(params)}`),
  goldenDiff: (a: string, b: string) => request<GoldenDiff>(`/api/golden/diff${q({ a, b })}`),
  gates: () => request<{ config: GateConfig; metrics: MetricInfo[] }>("/api/gates"),
  saveGates: (config: GateConfig) => request<{ config: GateConfig }>("/api/gates", { method: "PUT", body: JSON.stringify(config) }),
  settings: () => request<SettingsPayload>("/api/settings"),
  saveSettings: (values: Record<string, string | null>) =>
    request<SettingsPayload>("/api/settings", { method: "PUT", body: JSON.stringify({ values }) }),
  reportUrl: (runId: string, format: string) => `/api/runs/${encodeURIComponent(runId)}/report?format=${format}`,
};
