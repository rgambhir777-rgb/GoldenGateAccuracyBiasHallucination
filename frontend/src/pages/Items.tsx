import { X } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, Claim } from "../api";
import RunPicker from "../components/RunPicker";
import { Card, Empty, ErrorBox, Loading, PageHeader, Select, Tag } from "../components/ui";
import { pct } from "../format";
import { useAsync } from "../hooks";

const CLAIM_STYLE: Record<Claim["label"], string> = {
  supported: "bg-green-50 border-green-200 text-green-900",
  contradicted: "bg-red-50 border-red-200 text-red-900",
  unsupported: "bg-amber-50 border-amber-200 text-amber-900",
};

export default function Items() {
  const [params, setParams] = useSearchParams();
  const run = params.get("run") ?? "latest";
  const [category, setCategory] = useState("");
  const [slice, setSlice] = useState("");
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const selected = params.get("item");

  useEffect(() => { const t = window.setTimeout(() => setSearch(query), 250); return () => window.clearTimeout(t); }, [query]);
  const list = useAsync(() => api.items(run, { category, slice, status: status === "critical" ? undefined : status,
    critical: status === "critical" ? true : undefined, q: search }), [run, category, slice, status, search]);

  const set = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    setParams(next);
  };

  return (
    <div className="space-y-6">
      <PageHeader title="Item explorer" subtitle="Every golden item in a run: answer, retrieved chunks, citations and claim-level groundedness." />
      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <RunPicker value={run} onChange={(v) => set("run", v)} />
          <Select label="Category" value={category} onChange={setCategory}
            options={[{ value: "", label: "All categories" }, ...(list.data?.facets.categories ?? []).map((c) => ({ value: c, label: c }))]} />
          <Select label="Slice" value={slice} onChange={setSlice}
            options={[{ value: "", label: "All slices" }, ...(list.data?.facets.slices ?? []).map((s) => ({ value: s, label: s.replace(":", " = ") }))]} />
          <Select label="Status" value={status} onChange={setStatus} options={[
            { value: "", label: "All" }, { value: "fail", label: "Failing" }, { value: "pass", label: "Passing" },
            { value: "hallucinated", label: "Hallucinated" }, { value: "critical", label: "Critical only" }]} />
          <label className="flex flex-1 flex-col gap-1 text-xs font-medium text-slate-600">Search
            <input className="input" placeholder="question text or item id" value={query} onChange={(e) => setQuery(e.target.value)} />
          </label>
        </div>
      </Card>

      {list.loading ? <Loading /> : list.error ? <ErrorBox message={list.error} onRetry={list.reload} /> : !list.data?.items.length ? (
        <Empty title="No items match these filters" hint="Clear a filter or pick another run." />
      ) : (
        <Card title={`${list.data.count} of ${list.data.total} items`} subtitle={`Run ${list.data.run_id}`}>
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead><tr><th>Item</th><th>Question</th><th>Category</th><th className="num">Key facts</th><th>Claims</th><th>Result</th></tr></thead>
              <tbody>
                {list.data.items.map((i) => (
                  <tr key={i.item_id} className={`cursor-pointer hover:bg-slate-50 ${selected === i.item_id ? "bg-green-50" : ""}`}
                    onClick={() => set("item", i.item_id)}>
                    <td className="whitespace-nowrap"><code className="text-xs">{i.item_id}</code>
                      <div className="mt-1 flex gap-1">{i.critical && <Tag tone="red">critical</Tag>}{!i.answerable && <Tag tone="blue">unanswerable</Tag>}</div></td>
                    <td className="max-w-md">{i.question}{i.failure_reasons.length > 0 && <p className="mt-1 text-xs text-red-700">{i.failure_reasons.slice(0, 2).join("; ")}</p>}</td>
                    <td>{i.category}</td>
                    <td className="num">{i.answerable ? pct(i.key_fact_coverage, 0) : "–"}</td>
                    <td className="whitespace-nowrap text-xs">{i.n_claims} claims{i.n_bad_claims > 0 && <span className="ml-1 text-red-700">({i.n_bad_claims} bad)</span>}</td>
                    <td>{i.correct ? <Tag tone="green">pass</Tag> : <Tag tone="red">fail</Tag>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      {selected && <ItemPanel run={list.data?.run_id ?? run} itemId={selected} onClose={() => set("item", null)} />}
    </div>
  );
}

function ItemPanel({ run, itemId, onClose }: { run: string; itemId: string; onClose: () => void }) {
  const { data, error, loading } = useAsync(() => api.item(run, itemId), [run, itemId]);
  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label={`Item ${itemId}`}>
      <div className="absolute inset-0 bg-slate-900/40" onClick={onClose} />
      <div className="relative h-full w-full max-w-3xl overflow-y-auto bg-white p-6 shadow-xl">
        <button onClick={onClose} aria-label="Close" className="absolute right-4 top-4 rounded p-1 text-slate-500 hover:bg-slate-100"><X className="h-5 w-5" /></button>
        {loading ? <Loading /> : error ? <ErrorBox message={error} /> : data && (() => {
          const item = data.item;
          const j = item.judgment;
          return (
            <div className="space-y-5">
              <div>
                <div className="flex flex-wrap items-center gap-2"><code className="text-xs">{item.item_id}</code>
                  {item.correct ? <Tag tone="green">pass</Tag> : <Tag tone="red">fail</Tag>}{item.critical && <Tag tone="red">critical</Tag>}
                  <Tag>{item.category}</Tag><Tag>judge: {j.judge}</Tag>
                  {Object.entries(item.slices).map(([k, v]) => <Tag tone="blue" key={k}>{k}: {v}</Tag>)}</div>
                <h2 className="mt-2 text-lg font-semibold text-slate-900">{item.question}</h2>
                {item.failure_reasons.length > 0 && <ul className="mt-2 text-sm text-red-700">{item.failure_reasons.map((r) => <li key={r}>• {r}</li>)}</ul>}
                {j.notes.map((n) => <p key={n} className="mt-1 text-xs text-amber-700">{n}</p>)}
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <Box title="Reference answer">{item.reference_answer}</Box>
                <Box title="System answer" tone={item.correct ? "green" : "red"}>{item.response.answer || <em>(empty)</em>}
                  {item.response.error && <p className="mt-1 text-xs text-red-700">{item.response.error}</p>}</Box>
              </div>
              <section>
                <h3 className="mb-2 text-sm font-semibold text-slate-900">Key facts ({pct(item.key_fact_coverage, 0)} covered)</h3>
                {j.key_facts.length === 0 ? <p className="text-sm text-slate-500">Unanswerable item: the correct behaviour is to abstain. Abstained: {j.abstained ? "yes" : "no"}.</p> : (
                  <ul className="flex flex-wrap gap-2">{j.key_facts.map((f) => <li key={f.fact}><Tag tone={f.present ? "green" : "red"}>{f.present ? "✓" : "✗"} {f.fact}</Tag></li>)}</ul>
                )}
              </section>
              <section>
                <h3 className="mb-2 text-sm font-semibold text-slate-900">Claim-by-claim groundedness</h3>
                {j.claims.length === 0 ? <p className="text-sm text-slate-500">No factual claims (abstention or refusal).</p> : (
                  <table className="table-base"><thead><tr><th>Claim</th><th>Label</th><th>Cited</th><th>Supported by</th></tr></thead>
                    <tbody>{j.claims.map((c, idx) => (
                      <tr key={idx}><td><div className={`rounded border px-2 py-1 ${CLAIM_STYLE[c.label]}`}>{c.text}</div>
                        {c.evidence && c.label !== "supported" && <p className="mt-1 text-xs text-slate-500">Closest evidence: “{c.evidence}”</p>}</td>
                        <td><Tag tone={c.label === "supported" ? "green" : c.label === "contradicted" ? "red" : "amber"}>{c.label}</Tag></td>
                        <td className="text-xs">{c.cited_chunk_ids.join(", ") || "–"}</td><td className="text-xs">{c.supporting_chunk_ids.join(", ") || "–"}</td></tr>
                    ))}</tbody></table>
                )}
              </section>
              <section>
                <h3 className="mb-2 text-sm font-semibold text-slate-900">Citations</h3>
                {data.citations.length === 0 ? <p className="text-sm text-slate-500">No citations.</p> : (
                  <ul className="space-y-2">{data.citations.map((c) => (
                    <li key={c.chunk_id} className="rounded-lg border border-slate-200 p-2 text-sm">
                      <div className="flex flex-wrap gap-1"><code className="text-xs">{c.chunk_id}</code>
                        {!c.exists && <Tag tone="red">fabricated ID</Tag>}{c.gold && <Tag tone="blue">gold</Tag>}
                        {c.exists && <Tag tone={c.supports ? "green" : "amber"}>{c.supports ? "supports a claim" : "does not support any claim"}</Tag>}</div>
                      {c.text && <p className="mt-1 text-slate-600">{c.text}</p>}
                    </li>))}</ul>
                )}
              </section>
              <section>
                <h3 className="mb-2 text-sm font-semibold text-slate-900">Retrieved chunks (recall@k {pct(item.recall_at_k, 0)}, RR {item.reciprocal_rank?.toFixed(2) ?? "–"})</h3>
                <ol className="space-y-2">{data.retrieved.map((r) => (
                  <li key={r.chunk_id} className={`rounded-lg border p-2 text-sm ${r.gold ? "border-blue-200 bg-blue-50" : "border-slate-200"}`}>
                    <div className="flex flex-wrap items-center gap-2 text-xs"><span className="font-semibold">#{r.rank}</span><code>{r.chunk_id}</code>
                      <span className="text-slate-500">score {r.score.toFixed(2)}</span>{r.gold && <Tag tone="blue">gold</Tag>}</div>
                    <p className="mt-1 text-slate-600">{r.text}</p></li>))}</ol>
              </section>
              <p className="text-xs text-slate-400">Latency {item.response.latency_ms.toFixed(1)} ms · tokens {item.response.usage.prompt_tokens + item.response.usage.completion_tokens} · semantic match {pct(j.semantic_match, 0)} · decision {j.decision ?? "–"}</p>
            </div>
          );
        })()}
      </div>
    </div>
  );
}

function Box({ title, children, tone }: { title: string; children: React.ReactNode; tone?: "green" | "red" }) {
  const cls = tone === "green" ? "border-green-200 bg-green-50" : tone === "red" ? "border-red-200 bg-red-50" : "border-slate-200 bg-slate-50";
  return <div className={`rounded-lg border p-3 text-sm ${cls}`}><p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</p>{children}</div>;
}
