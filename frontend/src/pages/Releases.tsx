import { Flag, Play } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Card, Empty, ErrorBox, Loading, Notice, PageHeader, ProgressBar, Select, Tag, VerdictBadge } from "../components/ui";
import { fmtDate, pct } from "../format";
import { useAsync, useJob } from "../hooks";

export default function Releases() {
  const releases = useAsync(() => api.releases(), []);
  const systems = useAsync(() => api.systems(), []);
  const status = useAsync(() => api.status(), []);
  const [system, setSystem] = useState("release_1.3");
  const [golden, setGolden] = useState("latest");
  const [judge, setJudge] = useState("");
  const [release, setRelease] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const { job, error: jobError, track, setError } = useJob(() => releases.reload());

  const start = async () => {
    setError(null);
    try {
      track(await api.startRun({ system, golden, judge: judge || undefined, release: release || undefined }));
    } catch (e) { setError((e as Error).message); }
  };
  const makeBaseline = async (id: string) => {
    setBusy(id);
    try { await api.setBaseline(id); releases.reload(); } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  };
  const running = job && (job.status === "queued" || job.status === "running");
  const chosen = systems.data?.find((s) => s.id === system);

  return (
    <div className="space-y-6">
      <PageHeader title="Releases" subtitle="Every evaluated release with its prompt hash, model, golden version and verdict." />

      <Card title="Start a new run" subtitle="Runs the suite in the background; progress updates live.">
        <div className="flex flex-wrap items-end gap-3">
          <Select label="System" value={system} onChange={setSystem}
            options={(systems.data ?? [{ id: "release_1.3", label: "Demo release_1.3", available: true, description: "" }])
              .map((s) => ({ value: s.id, label: s.available ? s.label : `${s.label} (needs API key)` }))} />
          <Select label="Golden version" value={golden} onChange={setGolden}
            options={[{ value: "latest", label: "latest" }, ...(status.data?.golden_versions ?? []).map((v) => ({ value: v, label: v }))]} />
          <Select label="Judge" value={judge} onChange={setJudge}
            options={[{ value: "", label: "default (settings)" }, { value: "offline", label: "offline" }, { value: "auto", label: "auto" }, { value: "llm", label: "llm" }]} />
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">Release ID (optional)
            <input className="input" placeholder="e.g. release_2.0" value={release} onChange={(e) => setRelease(e.target.value)} />
          </label>
          <button className="btn-primary" onClick={start} disabled={!!running || (chosen ? !chosen.available : false)}>
            <Play className="h-4 w-4" /> Run suite
          </button>
        </div>
        {chosen && <p className="mt-2 text-xs text-slate-500">{chosen.description}{chosen.reason ? ` — ${chosen.reason}` : ""}</p>}
        {job && (
          <div className="mt-4 space-y-2">
            <ProgressBar done={job.done} total={job.total} label={job.status === "done" ? "Finished" : job.message || job.label} />
            {job.status === "done" && job.run_id && (
              <Notice tone="green">Run <code>{job.run_id}</code> finished. <Link className="underline" to={`/items?run=${job.run_id}`}>Explore items</Link></Notice>
            )}
            {job.status === "error" && <ErrorBox message={job.error ?? "Run failed"} />}
          </div>
        )}
        {jobError && <div className="mt-3"><ErrorBox message={jobError} /></div>}
      </Card>

      {releases.loading ? <Loading /> : releases.error ? <ErrorBox message={releases.error} onRetry={releases.reload} /> :
        !releases.data?.length ? <Empty title="No releases yet" hint="Start a run above or seed the demo data." /> : (
        <ol className="relative space-y-4 border-l-2 border-slate-200 pl-6">
          {releases.data.map((r) => (
            <li key={r.release_id} className="relative">
              <span className={`absolute -left-[33px] top-5 h-4 w-4 rounded-full border-2 border-white ${
                r.verdict === "SHIP" ? "bg-green-600" : r.verdict === "BLOCKED" ? "bg-red-600" : "bg-slate-400"}`} />
              <Card>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-lg font-semibold text-slate-900">{r.release_id}</h3>
                      <VerdictBadge verdict={r.verdict} size="sm" />
                      {r.is_baseline && <Tag tone="blue">baseline</Tag>}
                    </div>
                    <p className="mt-1 text-sm text-slate-600">{r.description}</p>
                  </div>
                  <div className="flex gap-2">
                    {!r.is_baseline && (
                      <button className="btn-secondary" disabled={busy === r.release_id} onClick={() => makeBaseline(r.release_id)}>
                        <Flag className="h-4 w-4" /> Set as baseline
                      </button>
                    )}
                    <Link className="btn-secondary" to={`/compare?current=${r.release_id}`}>Compare</Link>
                  </div>
                </div>
                <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3 lg:grid-cols-6">
                  <Meta k="Released" v={r.released_at ?? "–"} />
                  <Meta k="Model" v={r.model} />
                  <Meta k="Prompt hash" v={<code className="text-xs">{r.prompt_hash}</code>} />
                  <Meta k="Golden" v={r.golden_version} />
                  <Meta k="Retriever" v={`${String(r.retriever_config.retriever ?? "external")} · k=${String(r.retriever_config.top_k ?? "–")}`} />
                  <Meta k="Runs" v={String(r.run_count)} />
                </dl>
                <div className="mt-4 flex flex-wrap gap-4 text-sm">
                  <Metric k="Accuracy" v={pct(r.metrics.accuracy)} />
                  <Metric k="Hallucination" v={pct(r.metrics.hallucination_rate)} />
                  <Metric k="Citation precision" v={pct(r.metrics.citation_precision)} />
                  <Metric k="Max slice gap" v={pct(r.metrics.max_slice_gap)} />
                  <Metric k="CF consistency" v={pct(r.metrics.counterfactual_consistency)} />
                </div>
                {r.runs && r.runs.length > 1 && (
                  <details className="mt-3 text-sm">
                    <summary className="cursor-pointer text-slate-600">All runs ({r.runs.length})</summary>
                    <ul className="mt-2 space-y-1">
                      {r.runs.map((run) => (
                        <li key={run.run_id} className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
                          <code>{run.run_id}</code> · golden {run.golden_version} · {fmtDate(run.finished_at)} ·
                          accuracy {pct(run.metrics.accuracy)} <VerdictBadge verdict={run.verdict} size="sm" />
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </Card>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function Meta({ k, v }: { k: string; v: React.ReactNode }) {
  return <div><dt className="text-xs text-slate-500">{k}</dt><dd className="truncate font-medium text-slate-800">{v}</dd></div>;
}
function Metric({ k, v }: { k: string; v: string }) {
  return <div className="rounded-lg bg-slate-50 px-3 py-1.5"><span className="text-slate-500">{k} </span><span className="font-semibold tabular-nums">{v}</span></div>;
}
