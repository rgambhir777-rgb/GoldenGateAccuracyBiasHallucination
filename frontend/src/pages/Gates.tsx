import { Save, Undo2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api, GateConfig } from "../api";
import { Card, ErrorBox, Loading, Notice, PageHeader } from "../components/ui";
import { useAsync } from "../hooks";

const KIND_LABEL: Record<string, string> = {
  min: "at least", max: "at most", max_drop: "max drop vs baseline", max_increase: "max increase vs baseline", critical_items: "all must pass",
};

export default function Gates() {
  const { data, error, loading, reload } = useAsync(() => api.gates(), []);
  const [config, setConfig] = useState<GateConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ tone: "green" | "red"; text: string } | null>(null);
  useEffect(() => { if (data) setConfig(structuredClone(data.config)); }, [data]);

  if (loading) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!config || !data) return null;
  const labels = Object.fromEntries(data.metrics.map((m) => [m.name, m]));

  const localErrors = config.gates.flatMap((g) => {
    if (g.kind === "critical_items") return [];
    if (Number.isNaN(g.threshold)) return [`${g.id}: threshold must be a number`];
    const isRate = labels[g.metric ?? ""]?.kind === "rate";
    if (isRate && (g.threshold < 0 || g.threshold > 1)) return [`${g.id}: enter a value between 0 and 100%`];
    return [];
  });
  const dirty = JSON.stringify(config) !== JSON.stringify(data.config);

  const update = (idx: number, patch: Partial<GateConfig["gates"][number]>) =>
    setConfig({ ...config, gates: config.gates.map((g, i) => (i === idx ? { ...g, ...patch } : g)) });

  const save = async () => {
    setSaving(true);
    setMessage(null);
    try {
      await api.saveGates(config);
      setMessage({ tone: "green", text: "Gates saved to gates.yaml. New runs and comparisons use them immediately." });
      reload();
    } catch (e) {
      setMessage({ tone: "red", text: (e as Error).message });
    } finally { setSaving(false); }
  };

  return (
    <div className="space-y-6">
      <PageHeader title="Release gates" subtitle="A release ships only if every enabled gate passes. Stored in gates.yaml and used by the CLI, CI and dashboard."
        actions={<>
          <button className="btn-secondary" disabled={!dirty} onClick={() => setConfig(structuredClone(data.config))}><Undo2 className="h-4 w-4" /> Discard</button>
          <button className="btn-primary" disabled={!dirty || saving || localErrors.length > 0} onClick={save}><Save className="h-4 w-4" /> Save gates</button>
        </>} />
      {message && <Notice tone={message.tone}>{message.text}</Notice>}
      {localErrors.length > 0 && <Notice tone="red">{localErrors.join(" · ")}</Notice>}
      <Card title="Fairness settings">
        <label className="flex max-w-xs flex-col gap-1 text-xs font-medium text-slate-600">Minimum slice size (items)
          <input type="number" min={2} className="input" value={config.min_slice_size}
            onChange={(e) => setConfig({ ...config, min_slice_size: Number(e.target.value) })} />
        </label>
        <p className="mt-2 text-xs text-slate-500">Slices with fewer counterfactual items are reported but excluded from gap calculations.</p>
      </Card>
      <Card title="Thresholds">
        <div className="overflow-x-auto"><table className="table-base">
          <thead><tr><th>On</th><th>Gate</th><th>Metric</th><th>Rule</th><th>Threshold</th></tr></thead>
          <tbody>{config.gates.map((g, idx) => {
            const meta = labels[g.metric ?? ""];
            const isRate = meta?.kind === "rate";
            return (
              <tr key={g.id} className={g.enabled ? "" : "opacity-50"}>
                <td><input type="checkbox" aria-label={`Enable ${g.id}`} checked={g.enabled} onChange={(e) => update(idx, { enabled: e.target.checked })} /></td>
                <td><code className="text-xs">{g.id}</code><p className="text-xs text-slate-500">{g.description}</p></td>
                <td>{g.kind === "critical_items" ? "Critical items" : meta?.label ?? g.metric}</td>
                <td className="text-xs text-slate-600">{KIND_LABEL[g.kind]}</td>
                <td>{g.kind === "critical_items" ? <span className="text-xs text-slate-400">–</span> : (
                  <div className="flex items-center gap-1">
                    <input type="number" step={isRate ? 0.5 : 1} className="input w-24"
                      value={isRate ? +(g.threshold * 100).toFixed(2) : g.threshold}
                      onChange={(e) => update(idx, { threshold: isRate ? Number(e.target.value) / 100 : Number(e.target.value) })} />
                    <span className="text-xs text-slate-500">{isRate ? (g.kind.startsWith("max_") ? "pts" : "%") : ""}</span>
                  </div>
                )}</td>
              </tr>
            );
          })}</tbody></table></div>
      </Card>
    </div>
  );
}
