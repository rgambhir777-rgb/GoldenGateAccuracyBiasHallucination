import { useCallback, useEffect, useRef, useState } from "react";
import { api, Job } from "./api";

export interface AsyncState<T> { data: T | null; error: string | null; loading: boolean; reload: () => void }

/** Run an async loader whenever its dependencies change; exposes loading/error/reload. */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    loader()
      .then((d) => { if (alive) setData(d); })
      .catch((e: Error) => { if (alive) setError(e.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}

/** Poll a background job until it finishes. */
export function useJob(onDone?: (job: Job) => void) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  const doneRef = useRef(onDone);
  doneRef.current = onDone;

  const stop = () => { if (timer.current) window.clearInterval(timer.current); timer.current = null; };

  const track = useCallback((started: Job) => {
    stop();
    setError(null);
    setJob(started);
    timer.current = window.setInterval(async () => {
      try {
        const next = await api.job(started.id);
        setJob(next);
        if (next.status === "done" || next.status === "error") {
          stop();
          if (next.status === "done") doneRef.current?.(next);
        }
      } catch (e) {
        setError((e as Error).message);
        stop();
      }
    }, 400);
  }, []);

  useEffect(() => stop, []);
  return { job, error, track, setError };
}
