import { KeyRound, RotateCcw, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { Card, ErrorBox, Loading, Notice, PageHeader, ProgressBar, Select } from "../components/ui";
import { useAsync, useJob } from "../hooks";

export default function SettingsPage() {
  const { data, error, loading, reload } = useAsync(() => api.settings(), []);
  const [values, setValues] = useState<Record<string, string>>({});
  const [keys, setKeys] = useState<Record<string, string>>({ ANTHROPIC_API_KEY: "", OPENAI_API_KEY: "" });
  const [message, setMessage] = useState<{ tone: "green" | "red"; text: string } | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const { job, error: jobError, track } = useJob(() => setMessage({ tone: "green", text: "Demo data has been re-seeded." }));
  useEffect(() => { if (data) setValues({ ...data.values }); }, [data]);

  if (loading) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;

  const save = async (extra: Record<string, string | null> = {}) => {
    setMessage(null);
    try {
      const payload: Record<string, string | null> = { ...values, ...extra };
      Object.entries(keys).forEach(([k, v]) => { if (v.trim()) payload[k] = v.trim(); });
      await api.saveSettings(payload);
      setKeys({ ANTHROPIC_API_KEY: "", OPENAI_API_KEY: "" });
      setMessage({ tone: "green", text: "Settings saved to .env." });
      reload();
    } catch (e) { setMessage({ tone: "red", text: (e as Error).message }); }
  };
  const reset = async () => {
    setConfirmReset(false);
    try { track(await api.resetDemo()); } catch (e) { setMessage({ tone: "red", text: (e as Error).message }); }
  };
  const set = (k: string) => (v: string) => setValues({ ...values, [k]: v });
  const running = job && (job.status === "queued" || job.status === "running");

  return (
    <div className="space-y-6">
      <PageHeader title="Settings" subtitle={<>Saved locally to <code className="text-xs">{data.env_file}</code>. Environment variables override these values.</>} />
      {message && <Notice tone={message.tone}>{message.text}</Notice>}
      {data.judge.warning && <Notice>{data.judge.warning}</Notice>}

      <Card title="API keys" subtitle="Optional. Enables the LLM judge and the LLM RAG system. Keys are stored masked and never sent anywhere except the provider.">
        <div className="grid gap-4 md:grid-cols-2">
          {(["ANTHROPIC_API_KEY", "OPENAI_API_KEY"] as const).map((k) => (
            <div key={k} className="space-y-1">
              <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">{k}
                <input type="password" autoComplete="off" className="input" placeholder={data.keys[k] ?? "not set"} value={keys[k]}
                  onChange={(e) => setKeys({ ...keys, [k]: e.target.value })} />
              </label>
              <div className="flex items-center gap-2 text-xs text-slate-500"><KeyRound className="h-3.5 w-3.5" />
                {data.keys[k] ? <>stored: <code>{data.keys[k]}</code><button className="text-red-600 underline" onClick={() => save({ [k]: "" })}>remove</button></> : "no key stored"}</div>
            </div>
          ))}
        </div>
        <label className="mt-4 flex max-w-md flex-col gap-1 text-xs font-medium text-slate-600">OpenAI-compatible base URL
          <input className="input" value={values.OPENAI_BASE_URL ?? ""} onChange={(e) => set("OPENAI_BASE_URL")(e.target.value)} /></label>
      </Card>

      <Card title="Judge and models">
        <div className="flex flex-wrap gap-4">
          <Select label="Judge mode" value={values.GOLDENGATE_JUDGE_MODE ?? "auto"} onChange={set("GOLDENGATE_JUDGE_MODE")} options={[
            { value: "auto", label: "auto (LLM if a key is set)" }, { value: "offline", label: "offline only" }, { value: "llm", label: "LLM (falls back to offline)" }]} />
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">Judge model (Anthropic)
            <input className="input" value={values.GOLDENGATE_JUDGE_MODEL ?? ""} onChange={(e) => set("GOLDENGATE_JUDGE_MODEL")(e.target.value)} /></label>
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">RAG model (Anthropic)
            <input className="input" value={values.GOLDENGATE_RAG_MODEL ?? ""} onChange={(e) => set("GOLDENGATE_RAG_MODEL")(e.target.value)} /></label>
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">OpenAI-compatible model
            <input className="input" value={values.GOLDENGATE_OPENAI_MODEL ?? ""} onChange={(e) => set("GOLDENGATE_OPENAI_MODEL")(e.target.value)} /></label>
        </div>
        <p className="mt-2 text-xs text-slate-500">Currently effective: <strong>{data.judge.effective}</strong>{data.judge.provider ? ` via ${data.judge.provider}` : ""}.</p>
      </Card>

      <Card title="Retrieval and statistics">
        <div className="flex flex-wrap gap-4">
          <Select label="Retriever" value={values.GOLDENGATE_RETRIEVER ?? "bm25"} onChange={set("GOLDENGATE_RETRIEVER")}
            options={[{ value: "bm25", label: "BM25 (default)" }, { value: "tfidf", label: "TF-IDF cosine" }]} />
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">Top-k chunks (1–20)
            <input type="number" min={1} max={20} className="input w-28" value={values.GOLDENGATE_TOP_K ?? "5"} onChange={(e) => set("GOLDENGATE_TOP_K")(e.target.value)} /></label>
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">Bootstrap samples (100–20000)
            <input type="number" min={100} max={20000} className="input w-32" value={values.GOLDENGATE_BOOTSTRAP_SAMPLES ?? "1000"} onChange={(e) => set("GOLDENGATE_BOOTSTRAP_SAMPLES")(e.target.value)} /></label>
        </div>
        <button className="btn-primary mt-4" onClick={() => save()}><Save className="h-4 w-4" /> Save settings</button>
      </Card>

      <Card title="Demo data" subtitle="Deletes all runs and re-runs release_1.0–1.3 with the offline judge; release_1.0 becomes the baseline.">
        {!confirmReset ? (
          <button className="btn-danger" disabled={!!running} onClick={() => setConfirmReset(true)}><RotateCcw className="h-4 w-4" /> Reset demo data</button>
        ) : (
          <div className="flex flex-wrap items-center gap-2 text-sm"><span>This removes every run, including your own. Continue?</span>
            <button className="btn-danger" onClick={reset}>Yes, reset</button><button className="btn-secondary" onClick={() => setConfirmReset(false)}>Cancel</button></div>
        )}
        {job && <div className="mt-4"><ProgressBar done={job.done} total={job.total} label={job.status === "done" ? "Finished" : job.message || job.label} />
          {job.status === "error" && <div className="mt-2"><ErrorBox message={job.error ?? "Reset failed"} /></div>}</div>}
        {jobError && <div className="mt-2"><ErrorBox message={jobError} /></div>}
      </Card>
    </div>
  );
}
