import { Lock } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { Card, Empty, ErrorBox, Loading, PageHeader, Select, Tag } from "../components/ui";
import { useAsync } from "../hooks";

export default function Golden() {
  const versions = useAsync(() => api.golden(), []);
  const list = versions.data ?? [];
  const [version, setVersion] = useState("");
  const [kind, setKind] = useState("");
  const [query, setQuery] = useState("");
  const [diffA, setDiffA] = useState("v1");
  const [diffB, setDiffB] = useState("v2");
  const active = version || list[list.length - 1]?.version || "";
  useEffect(() => { if (list.length >= 2) { setDiffA(list[list.length - 2].version); setDiffB(list[list.length - 1].version); } }, [versions.data]); // eslint-disable-line
  const items = useAsync(() => active ? api.goldenItems(active, { kind, q: query }) : Promise.resolve(null), [active, kind, query]);
  const diff = useAsync(() => diffA && diffB && diffA !== diffB ? api.goldenDiff(diffA, diffB) : Promise.resolve(null), [diffA, diffB]);
  const vOpts = list.map((v) => ({ value: v.version, label: v.version }));

  return (
    <div className="space-y-6">
      <PageHeader title="Golden set" subtitle="Versioned, frozen evaluation datasets. Every run records the version and content hash it used." />
      {versions.loading ? <Loading /> : versions.error ? <ErrorBox message={versions.error} onRetry={versions.reload} /> : (
        <div className="grid gap-4 md:grid-cols-2">
          {list.map((v) => (
            <Card key={v.version} title={<span className="flex items-center gap-2">{v.version}{v.frozen && <Tag tone="blue"><Lock className="mr-1 h-3 w-3" />frozen</Tag>}
              {v.valid ? <Tag tone="green">valid</Tag> : <Tag tone="red">invalid</Tag>}</span>}
              subtitle={`${v.item_count} items · created ${v.created} · hash ${v.content_hash.slice(0, 12)}${v.parent ? ` · parent ${v.parent}` : ""}`}>
              <p className="text-sm text-slate-600">{v.description}</p>
              <h3 className="mt-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Changelog</h3>
              <ul className="mt-1 space-y-1 text-sm text-slate-700">{v.changelog.map((c) => <li key={c}>• {c}</li>)}</ul>
              {v.errors.map((e) => <p key={e} className="mt-2 text-sm text-red-700">✗ {e}</p>)}
            </Card>
          ))}
        </div>
      )}

      <Card title="Diff between versions" actions={<div className="flex gap-2">
        <Select label="From" value={diffA} onChange={setDiffA} options={vOpts} /><Select label="To" value={diffB} onChange={setDiffB} options={vOpts} /></div>}>
        {diffA === diffB ? <Empty title="Pick two different versions" /> : diff.loading ? <Loading /> : diff.error ? <ErrorBox message={diff.error} /> : diff.data && (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2 text-sm"><Tag tone="green">+{diff.data.added.length} added</Tag><Tag tone="red">−{diff.data.removed.length} removed</Tag>
              <Tag tone="amber">~{Object.keys(diff.data.changed).length} changed</Tag><Tag>{diff.data.unchanged} unchanged</Tag></div>
            {Object.keys(diff.data.changed).length > 0 && (
              <div className="overflow-x-auto"><table className="table-base"><thead><tr><th>Item</th><th>Field</th><th>Before</th><th>After</th></tr></thead>
                <tbody>{Object.entries(diff.data.details).flatMap(([id, fields]) => Object.entries(fields).map(([f, d]) => (
                  <tr key={id + f}><td><code className="text-xs">{id}</code></td><td>{f}</td>
                    <td className="bg-red-50 text-red-900">{JSON.stringify(d.before)}</td><td className="bg-green-50 text-green-900">{JSON.stringify(d.after)}</td></tr>)))}</tbody></table></div>
            )}
            {diff.data.added.length > 0 && <details><summary className="cursor-pointer text-sm text-slate-600">Added items ({diff.data.added.length})</summary>
              <p className="mt-2 flex flex-wrap gap-1">{diff.data.added.map((a) => <Tag key={a} tone="green">{a}</Tag>)}</p></details>}
            {diff.data.removed.length > 0 && <p className="flex flex-wrap gap-1">{diff.data.removed.map((a) => <Tag key={a} tone="red">{a}</Tag>)}</p>}
          </div>
        )}
      </Card>

      <Card title="Browse items" actions={<div className="flex flex-wrap items-end gap-2">
        <Select label="Version" value={active} onChange={setVersion} options={vOpts} />
        <Select label="Type" value={kind} onChange={setKind} options={[{ value: "", label: "All" }, { value: "factual", label: "Factual" },
          { value: "unanswerable", label: "Unanswerable" }, { value: "counterfactual", label: "Counterfactual" }]} />
        <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">Search<input className="input" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="question or id" /></label>
      </div>}>
        {items.loading ? <Loading /> : items.error ? <ErrorBox message={items.error} /> : !items.data?.items.length ? <Empty title="No items" /> : (
          <div className="max-h-[36rem] overflow-auto"><table className="table-base">
            <thead className="sticky top-0 bg-white"><tr><th>Item</th><th>Question</th><th>Key facts</th><th>Gold chunks</th><th>Meta</th></tr></thead>
            <tbody>{items.data.items.map((i) => (
              <tr key={i.id}><td><code className="text-xs">{i.id}</code></td><td className="max-w-sm">{i.question}<p className="mt-1 text-xs text-slate-500">{i.reference_answer}</p></td>
                <td className="text-xs">{i.key_facts.join(" · ") || <em>abstain</em>}</td><td className="text-xs">{i.gold_chunk_ids.join(", ") || "–"}</td>
                <td><div className="flex flex-wrap gap-1"><Tag>{i.category}</Tag><Tag>{i.difficulty}</Tag>{i.tags.map((t) => <Tag key={t} tone={t === "critical" ? "red" : "slate"}>{t}</Tag>)}
                  {Object.entries(i.slices).map(([k, v]) => <Tag key={k} tone="blue">{k}: {v}</Tag>)}</div></td></tr>
            ))}</tbody></table></div>
        )}
      </Card>
    </div>
  );
}
