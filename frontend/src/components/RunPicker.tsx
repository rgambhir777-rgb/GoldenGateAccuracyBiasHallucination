import { api } from "../api";
import { useAsync } from "../hooks";
import { Select } from "./ui";

/** Select a run: latest run of each release first, then every individual run. */
export default function RunPicker({ value, onChange, label = "Run" }: { value: string; onChange: (v: string) => void; label?: string }) {
  const runs = useAsync(() => api.runs(), []);
  const releases = Array.from(new Set((runs.data ?? []).map((r) => r.release_id))).sort();
  const options = [
    { value: "latest", label: "Latest run" },
    ...releases.map((r) => ({ value: r, label: `${r} (latest)` })),
    ...(runs.data ?? []).map((r) => ({ value: r.run_id, label: `${r.run_id} · golden ${r.golden_version}` })),
  ];
  return <Select label={label} value={value} onChange={onChange} options={options} className="min-w-[14rem]" />;
}
