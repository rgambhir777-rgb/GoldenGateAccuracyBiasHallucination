# GoldenGate architecture

GoldenGate evaluates a retrieval-augmented generation (RAG) system against a versioned golden
dataset, scores every answer for accuracy, groundedness, citation quality and fairness, and turns
the results into a SHIP / BLOCKED decision that CI can enforce.

## Components

```mermaid
flowchart LR
  subgraph Inputs
    C[corpus/*.md<br/>40 policy docs]
    G[golden/vN<br/>items.jsonl + manifest]
    R[rubrics/judge_v1.md]
    Y[gates.yaml]
  end

  subgraph Systems["systems/ (RAGSystem interface)"]
    D[Demo releases 1.0–1.3<br/>BM25 + extractive answers]
    L[LLM RAG<br/>retriever + Claude / OpenAI-compatible]
    H[HTTP adapter<br/>any external service]
    P[JSONL replay<br/>recorded outputs]
  end

  subgraph Core["goldengate core"]
    RET[retrieval/<br/>chunker, BM25, TF-IDF]
    J[judges/<br/>offline + LLM judge + cache]
    M[metrics/<br/>scoring, aggregates, bootstrap CIs]
    F[fairness/<br/>slices, gaps, significance,<br/>counterfactual consistency]
    GT[gates/<br/>config + engine]
    REL[releases/<br/>runner, store, compare, history]
  end

  subgraph Interfaces
    CLI[Typer CLI + Rich]
    API[FastAPI /api]
    UI[React dashboard<br/>frontend/dist]
    PT[pytest tests/evals]
    REP[reports/<br/>HTML, MD, JSON, JUnit]
  end

  DB[(SQLite<br/>releases, runs, metrics,<br/>settings, judge cache)]
  JS[(data/runs/*.json<br/>full item results)]

  C --> RET --> D & L
  G --> REL
  D & L & H & P --> REL
  REL --> J --> M --> F --> GT
  R --> J
  Y --> GT
  REL <--> DB
  REL <--> JS
  J <--> DB
  REL --> CLI & API & PT & REP
  API --> UI
```

## Evaluation pipeline

```mermaid
flowchart TD
  A[Golden set vN<br/>validate schema + frozen hash] --> B[For each item:<br/>system.answer question, user_context]
  B --> C[Response<br/>answer, citations, retrieved chunks, latency, tokens]
  C --> D{Judge}
  D -->|key set, mode auto/llm| E[LLM judge<br/>rubric judge-v1, strict JSON,<br/>retries, cache by rubric+item+answer hash]
  D -->|no key or error| O[Offline judge<br/>rapidfuzz facts, quantity checks,<br/>sentence overlap groundedness]
  E -->|failure| O
  E & O --> S[Per-item scores<br/>correct, coverage, claims S/C/U,<br/>citation precision/recall, fabricated IDs,<br/>recall@k, reciprocal rank]
  S --> AG[Aggregate metrics<br/>+ bootstrap 95% CIs]
  S --> FS[Fairness on counterfactual items<br/>per-slice metrics, max gaps,<br/>two-proportion test, consistency]
  AG & FS --> GA[Gates vs baseline run<br/>min / max / max_drop / max_increase / critical]
  GA --> V{Verdict}
  V -->|all pass| SHIP[SHIP]
  V -->|any fail| BLK[BLOCKED + reasons]
  SHIP & BLK --> OUT[Run JSON + SQLite index]
  OUT --> RP[HTML report · Markdown PR comment · JSON · JUnit]
  OUT --> DASH[Dashboard]
  OUT --> CI[GitHub Actions<br/>PR comment, artifact, failing check]
```

## Release tracking

```mermaid
sequenceDiagram
  participant Dev as Pull request
  participant CI as regression-suite.yml
  participant Main as record-baseline.yml
  participant Night as nightly-drift.yml
  Dev->>CI: change prompt / model / retriever (release.yaml)
  CI->>CI: import baselines/baseline.json
  CI->>CI: run suite, compare, gate
  CI-->>Dev: PR comment (metrics, gates, slices) + HTML artifact
  CI-->>Dev: check fails if BLOCKED
  Dev->>Main: merge to main / tag
  Main->>Main: re-run, require SHIP
  Main->>Main: commit new baselines/baseline.json
  Night->>Night: daily re-run vs baseline (LLM judge/system if keys)
  Night-->>Dev: issue opened if drift blocks the release
```

## Key design decisions

| Decision | Why |
|---|---|
| One run = one JSON file + SQLite index | JSON keeps full item-level evidence portable (CI baseline is a committed run file); SQLite gives fast listing, trends and baseline settings. |
| Section-level chunks with stable slug IDs (`doc#section`) | Citations and gold labels survive re-ordering of documents. |
| Offline judge always available | The whole project runs with no API key; the LLM judge is an upgrade, not a dependency. Every item records which judge scored it. |
| LLM judge falls back per item and disables itself after repeated auth/connection errors | An invalid or missing key never crashes a run or the dashboard. |
| Fairness measured on counterfactual groups only | Variants differ only by a persona cue, so a gap is attributable to the cue and not to question difficulty. |
| Paired bootstrap for deltas | Release comparisons resample the same items in both runs, so CIs reflect the change, not item mix. |
| Gates use point estimates; CIs and p-values are reported next to them | Gates must be deterministic in CI; the intervals show whether a near-threshold change is noise. |
| Frontend built into `frontend/dist` and served by FastAPI | One process on one port; end users do not need Node.js. |

## Module map

| Path | Responsibility |
|---|---|
| `goldengate/core` | Pydantic models, text utilities (sentences, quantities, citations) |
| `goldengate/retrieval` | Markdown chunker, BM25 and TF-IDF retrievers |
| `goldengate/systems` | `RAGSystem` interface, demo releases, LLM RAG, HTTP and replay adapters, registry |
| `goldengate/golden` | Load, validate, diff, freeze and create golden versions |
| `goldengate/judges` | Offline judge, LLM judge, judge factory |
| `goldengate/llm` | Anthropic SDK and OpenAI-compatible JSON clients |
| `goldengate/metrics` | Per-item scoring, metric catalogue, bootstrap, citation and retrieval metrics |
| `goldengate/fairness` | Slice statistics, gaps, significance, counterfactual consistency |
| `goldengate/gates` | `gates.yaml` schema and the gate engine |
| `goldengate/releases` | SQLite models, run store, runner, comparison, history |
| `goldengate/reports` | Markdown / HTML / JSON / JUnit renderers and inline SVG charts |
| `goldengate/cli` | Typer commands |
| `goldengate/server` | FastAPI app, background jobs, launcher |
