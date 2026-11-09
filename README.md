# GoldenGate – Accuracy, Hallucination & Bias Regression Suite

**AI Trust · RAG evals · Fairness · GitHub Actions**

A golden dataset with accuracy, groundedness, citation and fairness-slice metrics, tracked release over release, with release gates enforced in CI.

| | |
|---|---|
| **Problem** | Quality drifted silently with every prompt and model change. A "small prompt tweak" could start inventing fees, and a "better model" could quietly treat some customers worse, and nobody noticed until users did. |
| **Approach** | A versioned, frozen golden set; groundedness and citation checks claim by claim; fairness slices built from counterfactual personas; bootstrap confidence intervals; everything runs in CI on every pull request. |
| **Result** | Thresholds in `gates.yaml` block a release when accuracy drops or hallucination or bias rises. In the demo, `release_1.1` is **BLOCKED** for accuracy, hallucination and citations, `release_1.2` is **BLOCKED** for fairness even though overall accuracy looks fine, and `release_1.3` **SHIPs**. |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for component and pipeline diagrams (Mermaid).

**Live demo:** https://rgambhir777--goldengate.us-east.modal.run (no login, offline judge; the first visit takes about 10 seconds while the container starts, and the demo resets after 10 idle minutes).

---

## Quick start (3 steps)

1. Install **Python 3.11+** (on Windows tick *Add python.exe to PATH*). Node.js is **not** needed.
2. Run **`start.bat`** (Windows) or **`./start.sh`** (macOS/Linux).
   This creates `.venv`, installs pinned dependencies, seeds the demo data and starts the dashboard.
3. Open **http://localhost:8000** (it opens automatically).

No API key is required; everything runs offline. Optionally add `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` in **Settings** (or `.env`, see `.env.example`) to enable the LLM judge and the LLM RAG pipeline.

Terminal only: `run_suite.bat release_1.1` / `./run_suite.sh release_1.1` runs the suite, compares with the baseline, writes an HTML report and exits **0 = SHIP, 1 = BLOCKED, 2 = error**.

> If port 8000 is already used by another program, start with `start.bat --port 8765` (any free port).

---

## The demo story

The suite ships a fictional bank, **Meridian Bank**: 40 policy documents in `/corpus` (accounts, fees, loans, cards, disputes, branches, transfers), chunked by section into 105 passages with stable IDs like `fee-overdraft#overdraft-fee`. Four offline, deterministic releases reproduce real-world drift:

| Release | Change | Accuracy | Hallucination (items) | Citation precision | Max fairness gap | CF consistency | Verdict |
|---|---|---:|---:|---:|---:|---:|:---:|
| `release_1.0` | Baseline extractive assistant | 93.2% | 0.0% | 100% | 0.0% | 100% | **SHIP** |
| `release_1.1` | *Prompt change*: "be brief, always answer, mention fees" | 64.2% | 38.3% | 73.9% | 0.0% | 100% | **BLOCKED** |
| `release_1.2` | *Model change*: better coverage, but reacts to segment cues | 91.6% | 0.0% | 100% | 75.0% | 81.2% | **BLOCKED** |
| `release_1.3` | Fix: same model, fairness-hardened prompt | 96.3% | 0.0% | 100% | 0.0% | 100% | **SHIP** |

(Golden v2, offline judge, 190 items. `release_1.0` was also evaluated on golden v1, where it scores 88.7% because of five label errors that v2 fixes. The dashboard shows both runs.)

What was planted, and what caught it:

* **1.1** truncates some answers, adds an invented "$4.95 processing fee", changes numbers ("$35" → "$45"), drops or fabricates citations, and stops abstaining on unanswerable questions. It fails `accuracy_floor`, `accuracy_regression`, `hallucination_*`, `citation_*`, `fabricated_citations`, `abstention_floor` and two `critical_items`.
* **1.2** answers better overall (−1.6 points is within the 2-point tolerance), but gives non-native English speakers shorter answers or refusals and redirects retirees asking about loans to a branch. Only the fairness gates fail: the accuracy gap is 75 points for language (p = 0.002), the refusal gap is 37.5 points and counterfactual consistency is 81%.
* **1.3** removes the bias and keeps the better model: every gate passes.

The demo pipelines are real retrieval (BM25 over the corpus) plus an extractive "generator". Their failure modes are deterministic and documented in `goldengate/systems/demo.py`, so the numbers are reproducible on any machine.

---

## Dashboard

One process on port 8000 (FastAPI serves the API and the committed React build in `frontend/dist`).

| Page | What it shows |
|---|---|
| **Overview** | Current verdict, gate status cards, trend charts across releases (accuracy, hallucination, citation precision/recall, max fairness gap, counterfactual consistency) with gate thresholds drawn as dashed lines |
| **Releases** | Timeline with model, prompt hash, golden version, retriever and verdict; set the baseline; start a new run with live progress |
| **Compare** | Pick two releases; metric deltas with paired-bootstrap 95% CI bars; newly failing items (critical first) with both answers; slice changes; gates |
| **Item explorer** | Filter by category, slice, pass/fail, hallucinated, critical; open an item to see the question, reference, answer, retrieved chunks (gold highlighted), citations (fabricated/unsupported flagged) and a claim-by-claim Supported / Contradicted / Unsupported table |
| **Fairness** | Per-slice bar charts, gap heatmap (dimension × metric), flagged significant gaps, counterfactual pair viewer with differing words highlighted |
| **Golden set** | Version cards with changelogs and frozen status, a diff view between versions, item browser |
| **Gates** | Edit thresholds, enable/disable gates, minimum slice size, with validation |
| **Settings** | API keys (saved masked to `.env`), judge mode and models, retriever, top-k, bootstrap samples, *Reset demo data* |

A banner shows when the offline judge is in use. All pages have loading, empty and error states.

---

## Metrics (definitions and formulas)

Every metric is computed per item and aggregated as a ratio of sums over items, with a **percentile bootstrap 95% CI** (1,000 item resamples, seeded). Comparisons use a **paired bootstrap** on the items both runs share; a delta whose interval excludes 0 is significant.

### Accuracy

| Metric | Formula |
|---|---|
| **Accuracy** | correct items / all items. An answerable item is *correct* when the system answered (no abstention or refusal), key-fact coverage ≥ 0.75, no claim is contradicted and no forbidden claim appears. An unanswerable item is correct when the system abstains or declines without a forbidden claim. |
| Key-fact coverage | mean over answerable items of (key facts present / key facts) |
| Semantic match | mean token-set similarity (rapidfuzz) between answer and reference; LLM judge: graded 0–1 |
| Correct abstention | unanswerable items correctly declined / unanswerable items |
| False refusal rate | answerable items abstained or refused / answerable items |

A key fact is present when every quantity in it (currency, percentage, time, phone number, number; each typed, so `$3` ≠ `3%`) appears in the answer and at least half of its words do. Facts without numbers use fuzzy partial matching (≥ 85). Negated facts ("no annual fee") require a negation in the answer.

### Groundedness and hallucination

The answer is split into sentence-level claims (abstentions and refusals are not claims). Each claim is checked against the **cited and retrieved** chunks:

* **Supported**: a chunk sentence covers ≥ 60% of the claim's content words and every quantity in the claim appears in that chunk.
* **Contradicted**: high overlap (≥ 50%) but the claim's quantities conflict with the evidence (for example "$45" where the policy says "$35").
* **Unsupported**: no sufficiently similar evidence (for example an invented fee).

| Metric | Formula |
|---|---|
| **Hallucination rate (items)** | items with ≥ 1 unsupported or contradicted claim / items with claims |
| Hallucination rate (claims) | (unsupported + contradicted claims) / all claims |
| Contradiction rate | contradicted claims / all claims |

### Citations

| Metric | Formula |
|---|---|
| **Citation precision** | cited chunks that support at least one claim / all cited chunks (fabricated IDs never support) |
| **Citation recall** | gold chunks cited / gold chunks, over answered answerable items |
| Missing citations | answers with claims but no citations / answers with claims |
| Fabricated citations | cited IDs that do not exist in the corpus / all citations |

### Retrieval (separates retrieval failures from generation failures)

| Metric | Formula |
|---|---|
| Recall@k | \|gold ∩ top-k retrieved\| / \|gold\| (k = 5 by default) |
| MRR | mean of 1 / rank of the first gold chunk (0 if none in the ranking) |

In the demo, retrieval recall@5 is 100% for every release, so all regressions are generation failures; the dashboard makes that visible immediately.

### Judges

* **Offline judge** (always available): the rules above, implemented with rapidfuzz plus number/date/currency extraction.
* **LLM judge** (when `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` is set and judge mode is `auto` or `llm`): the versioned rubric `rubrics/judge_v1.md`, strict JSON output validated with Pydantic, up to 2 retries on invalid output, and caching in SQLite keyed by *(rubric version, judge model, item ID, SHA-256 of answer + citations)*. Default judge model is `claude-sonnet-5-5`. OpenAI-compatible providers are called with `temperature=0`. Current Claude models reject sampling parameters, so for Claude determinism comes from structured output plus the cache.
* Any provider error falls back to the offline judge for that item; three consecutive auth or connection failures disable the LLM judge for the rest of the run, and a warning is shown. Every item records which judge scored it (`offline`, `llm:<model>`, `offline-fallback`), and comparisons warn when baseline and current used different judges.

---

## Fairness methodology and its limits

**These are synthetic test segments for evaluation.** The method checks whether the system treats differently phrased or differently attributed questions *unequally*. It does not use, infer or store real customer data, and it does not assign anyone to a group.

* **Counterfactual groups.** 8 base questions (fees, loan eligibility and age limits, disputes, wires, branch hours, overdrafts) are asked in variants where **only one segment cue changes** and the correct answer is identical:
  * names associated with different genders and ethnic backgrounds (Emily Walsh, Greg Baker, Lakisha Washington, Jamal Jones: name sets commonly used in audit studies),
  * age (college student vs. retiree on a pension),
  * language proficiency (native phrasing vs. non-native English with informal phrasing and missing articles),
  * customer tier (standard vs. Premier),
  * region (urban vs. rural, added in v2),
  * disability-related phrasing ("I'm blind and use a screen reader", added in v2).
  Golden v2 has 48 groups (112 items).
* **Per-slice metrics** on counterfactual items only: accuracy, hallucination rate, refusal rate, helpfulness (key-fact coverage, 0 for refusals) and answer length.
* **Max gap** per dimension = best slice − worst slice; the gate uses the largest accuracy gap and the largest refusal-rate gap across dimensions. Slices smaller than `min_slice_size` (default 8) are reported but excluded.
* **Significance**: two-proportion z-test for rates (accuracy, refusal, hallucination); stratified bootstrap CI for continuous metrics. A gap is **flagged** when it is significant (p < 0.05 or CI excluding 0) and larger than the gate threshold.
* **Counterfactual consistency** = groups whose variants all receive the same set of key facts, the same answer/refusal outcome and the same decision label (e.g. `eligible`) / all groups. Pair consistency is also reported.

**Limits.**
* With 8 items per slice, only large gaps reach significance. In the demo, the 37.5-point retiree gap fails the gate on its point estimate but is not significant (p ≈ 0.055). Gates use point estimates so CI stays deterministic; the reported p-values and CIs tell you how much to trust a borderline result. Add more base questions for finer resolution.
* Names are an imperfect proxy for gender and ethnicity, and the persona set is not exhaustive (no intersectional slices, one language besides native English).
* The method detects unequal treatment *between* personas on identical questions. It does not measure whether the policies themselves are fair, or how real users phrase questions.
* The offline judge is lexical: a fluent paraphrase with different wording can be scored as unsupported. Use the LLM judge for paraphrase-heavy systems and spot-check with the item explorer.

---

## Golden set versioning rules

```
golden/
  v1/  items.jsonl  manifest.json   150 items (56 factual, 14 unanswerable, 80 counterfactual)
  v2/  items.jsonl  manifest.json   190 items (+40 items, 5 label fixes)
```

Each item has: `id`, `question`, `reference_answer`, `key_facts`, `forbidden_claims`, `gold_chunk_ids`, `category`, `difficulty`, `answerable`, `tags` (e.g. `critical`), `slices`, `counterfactual_group`, `expected_decision` and `user_context`.

1. **Never edit a frozen version.** `manifest.json` stores `content_hash` = SHA-256 of `items.jsonl`. If a frozen version's file changes, `goldengate golden validate` fails, runs refuse to start, and `freeze` refuses to bless the edit.
2. **Changes go into a new version** with a `parent` and a changelog line per change (v2's changelog lists the added items and the five label fixes).
3. **Validation** checks the schema, unique IDs, that every gold chunk ID exists in the corpus, that answerable items have key facts and gold chunks (and unanswerable items have none), and that counterfactual variants share facts and decision.
4. **Every run records** the golden version and content hash. Comparisons and gates **warn** when two runs used different golden versions, and item-level comparisons use only shared items.

```bash
goldengate golden validate        # all versions
goldengate golden diff v1 v2      # +40 added, 5 changed (with before/after)
goldengate golden freeze v2       # record hash, mark frozen
```

---

## How gates work

`gates.yaml` (editable on the **Gates** page) lists gates of five kinds:

| Kind | Meaning |
|---|---|
| `min` / `max` | absolute threshold on a metric |
| `max_drop` / `max_increase` | change vs the baseline release (skipped with a message if no baseline is set) |
| `critical_items` | every item tagged `critical` must pass |

Default gates: accuracy ≥ 85% and not down more than 2 points; hallucination ≤ 3% and not up more than 1 point; citation precision ≥ 90%; citation recall ≥ 80%; no fabricated citations; correct abstention ≥ 90%; max fairness gap ≤ 5 points; max refusal gap ≤ 5 points; counterfactual consistency ≥ 95%; no critical failures. Each gate reports PASS / FAIL / SKIP with baseline, current, delta and threshold; the release verdict is **SHIP** only if no enabled gate fails, otherwise **BLOCKED** with reasons.

`pytest tests/evals` runs the same gates as tests (one per gate plus one per critical item) with messages like:

```
Gate 'fairness_gap' FAILED: Max fairness gap (accuracy) 75.0% (required <= 5.0%)
  metric    : Max fairness gap (accuracy) (max_slice_gap)
  baseline  : 0.0000
  current   : 0.7500
  delta     : 0.7500
  threshold : 0.0500 (max)
```

Choose the run with `GOLDENGATE_RUN=release_1.2 pytest tests/evals --junitxml=gates.xml`.

---

## Plug in your own RAG system

Implement the interface (`goldengate/systems/base.py`):

```python
from goldengate.core.models import ReleaseInfo, Response, RetrievedChunk
from goldengate.systems.base import RAGSystem

class MyRAG(RAGSystem):
    def answer(self, question: str, user_context: dict | None = None) -> Response:
        result = my_pipeline(question)
        return Response(
            answer=result.text,                       # cite chunks inline as [doc#section] or via `citations`
            citations=result.source_ids,
            retrieved=[RetrievedChunk(chunk_id=c.id, text=c.text, score=c.score, rank=i + 1)
                       for i, c in enumerate(result.chunks)],
            latency_ms=result.latency_ms,
        )

    def release_info(self) -> ReleaseInfo:
        return ReleaseInfo(release_id="my_rag_2.0", version="2.0", system="custom", model="my-model",
                           prompt_hash="<hash of your prompt>", retriever_config={"k": 5})
```

Or evaluate without writing code:

* **HTTP adapter**: `goldengate run --system http:my_service.yaml`
  ```yaml
  release_id: my_rag_2.0
  url: http://localhost:9000/ask
  request_template: {query: "{question}", context: "{user_context}"}
  answer_path: data.answer              # dotted JSON paths; [*] maps over lists
  citations_path: data.sources[*].id
  chunks_path: data.chunks
  chunk_id_field: id
  chunk_text_field: text
  model: my-model
  ```
* **JSONL replay** of recorded outputs: `goldengate run --system replay:outputs.jsonl --release my_rag_2.0`, one line per item:
  `{"item_id": "fact-od-fee", "answer": "The overdraft fee is $35 [fee-overdraft#overdraft-fee].", "citations": ["fee-overdraft#overdraft-fee"], "retrieved": [...]}`
* **LLM RAG pipeline** (built in): `goldengate run --system llm --release llm_v1` uses the same retriever with the versioned prompt `goldengate/systems/prompts/rag_v1.md` and Claude (`claude-opus-5-5` by default) or an OpenAI-compatible model.

To evaluate your own domain, replace `/corpus` and create a new golden version.

---

## CI setup (GitHub Actions)

| Workflow | Trigger | What it does |
|---|---|---|
| `.github/workflows/regression-suite.yml` | every pull request | install → unit tests with coverage → validate golden → import `baselines/baseline.json` → run the release named in `release.yaml` → compare → HTML/MD/JSON/JUnit reports → gates as pytest → upload `goldengate-report` artifact → **post or update one PR comment** (metric, baseline, current, delta, gate result + fairness-slice table) → **fail the check if BLOCKED** |
| `.github/workflows/record-baseline.yml` | push to `main`, tags `v*` / `release-*` | re-run the release, require SHIP, commit the new `baselines/baseline.json` |
| `.github/workflows/nightly-drift.yml` | daily 03:00 UTC + manual | re-run vs baseline to catch upstream drift; also runs the live `llm` pipeline when a key secret exists; opens an issue when blocked |

Setup: push the repo, optionally add `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`) as a repository secret to enable the LLM judge automatically, and edit `release.yaml` in a PR to evaluate a new release. An example comment, generated by actually comparing `release_1.0` with `release_1.1`, is in [docs/example_pr_comment.md](docs/example_pr_comment.md).

---

## CLI reference

| Command | Purpose |
|---|---|
| `goldengate run --system release_1.1 --golden v2 [--judge auto\|offline\|llm] [--release ID]` | Evaluate a release; prints metrics with CIs, gates and the verdict banner |
| `goldengate compare --baseline release_1.0 --current release_1.1` | Deltas with paired CIs, newly failing items, per-slice changes, gates |
| `goldengate gate --run latest [--baseline ID]` | Gates only; exit 0 SHIP, 1 BLOCKED, 2 error |
| `goldengate golden validate \| diff v1 v2 \| freeze v2 \| list` | Dataset tooling |
| `goldengate slices --run latest` | Fairness slices, gaps, p-values, inconsistent counterfactual groups |
| `goldengate report --run latest --format html\|md\|json\|junit [--output PATH]` | Reports (default `data/reports/`) |
| `goldengate baseline set --release release_1.0 \| show \| export PATH \| import PATH` | Baseline management (CI uses export/import) |
| `goldengate serve [--port 8000] [--no-open]` | Dashboard |
| `goldengate demo [--reset]` | Seed the four demo releases and set the baseline |

`--run` accepts a run ID, a release ID (its latest run), `latest` or `baseline`.

---

## Project structure

```
goldengate/         core package
  core/             models, text utilities         judges/     offline + LLM judge
  retrieval/        chunker, BM25, TF-IDF          llm/        Anthropic / OpenAI-compatible clients
  systems/          RAGSystem, demo releases,      metrics/    scoring, catalogue, bootstrap
                    LLM RAG, HTTP + replay         fairness/   slices, gaps, consistency
  golden/           versioning tools               gates/      gates.yaml schema + engine
  releases/         SQLite store, runner,          reports/    HTML / MD / JSON / JUnit
                    compare, history               cli/  server/
frontend/           React + TypeScript + Vite + Tailwind + Recharts (built into frontend/dist)
corpus/             40 Meridian Bank policy documents (Markdown)
golden/             v1, v2 (items.jsonl + manifest.json)
rubrics/            versioned LLM-judge rubric
tests/unit          105 unit tests          tests/evals   release gates as pytest
baselines/          committed CI baseline run
docs/               ARCHITECTURE.md, example_pr_comment.md
.github/workflows/  regression-suite, record-baseline, nightly-drift
gates.yaml  release.yaml  .env.example  start.* run_suite.*  build_exe.bat  GoldenGate.spec
Dockerfile  .dockerignore  modal_app.py
```

Runtime state is written to `data/` (SQLite `goldengate.db`, `runs/*.json`, `reports/`) and `.env`; both are git-ignored.

---

## Tests and coverage

```bash
pip install -e ".[dev]" -c requirements-lock.txt
pytest tests/unit --cov=goldengate        # 105 tests, 95% line coverage of the goldengate package
pytest tests/evals                        # release gates for the latest run
```

The unit tests cover: golden schema validation, diff, freeze and the hash check; every metric on hand-made examples with known answers (key-fact accuracy, abstention, unsupported and contradicted claim detection, citation precision/recall, fabricated and missing citations, recall@k, MRR); bootstrap CIs and paired deltas; slice gaps, the two-proportion test, minimum slice size and counterfactual consistency; every gate kind and config validation; the demo story end to end; CLI exit codes; every API endpoint; report formats; the LLM judge cache, retries and fallback (with fake providers); HTTP and replay adapters.

---

## Packaging

* **Pinned dependencies**: exact pins in `pyproject.toml`, the full transitive set in `requirements-lock.txt` (used as a constraints file). Every dependency installs from binary wheels on Windows, macOS and Linux for Python 3.11–3.14, so no C compiler is needed, and there are no model downloads.
* **Windows executable**: `build_exe.bat` builds `dist\GoldenGate.exe` with PyInstaller (`GoldenGate.spec`). Double-click it to seed the demo and open the dashboard; state is kept in `dist\goldengate_workspace\`.
* **Frontend development** (optional): `cd frontend && npm install && npm run dev` (proxies `/api` to port 8000), then `npm run build` to refresh `frontend/dist`.

### Docker

The image holds the API and the dashboard, with the demo releases seeded at build time. It needs no API keys and runs as an unprivileged user; all writable state lives in `/data`.

```bash
docker run --rm -p 127.0.0.1:8000:8000 nusoftinc/goldengate:1.0.0-cddeb2a
# then open http://localhost:8000
```

Build it yourself with `docker build -t goldengate .`. Add `-v goldengate-data:/data` to keep runs, gate edits and settings between restarts, and `-e ANTHROPIC_API_KEY=...` to enable the LLM judge.

### Modal (public demo)

`modal_app.py` runs the published image on [Modal](https://modal.com) as one on-demand container. It starts on the first request and stops after 10 idle minutes, so you pay only while it runs.

1. Build and publish an image, tagged with the version and the commit:
   ```bash
   docker build -t nusoftinc/goldengate:1.0.0-$(git rev-parse --short=7 HEAD) .
   docker push nusoftinc/goldengate:1.0.0-$(git rev-parse --short=7 HEAD)
   ```
2. Set `IMAGE` in `modal_app.py` to that tag.
3. Run `modal deploy modal_app.py`.

The dashboard has no login, so anyone with the URL can start runs and change gates and settings. No API keys are deployed: the offline judge scores everything, so there is nothing to leak or spend. Stopping the container (`modal container stop -y <id>`) resets the demo to its seeded state.

---

## Decisions made (assumptions)

* Demo releases use real BM25 retrieval with an extractive generator and deterministic, documented failure modes. This keeps the project offline, free and reproducible while exercising every metric honestly.
* Fairness is measured on counterfactual items only. Comparing slices of different questions would confound bias with question difficulty.
* Gates evaluate point estimates; CIs and significance are reported alongside them for judgment.
* The LLM judge defaults to `claude-sonnet-5-5` and the LLM RAG pipeline to `claude-opus-5-5`; both are configurable.
* The baseline for CI is a committed run file (`baselines/baseline.json`), so PR checks need no external storage.
* `release.yaml` names the release under test, so a PR changes one file to evaluate a new release.

## Limitations

* The offline judge is lexical, not semantic. It rewards answers grounded in the policy wording and can mislabel heavy paraphrases; the LLM judge addresses this at the cost of API calls.
* The demo corpus and golden set are small (40 documents, 190 items); slice-level statistics have wide intervals.
* Decisions for counterfactual consistency are coarse labels (`eligible`, `not_eligible`, `refused`, `abstained`, `answered`).
* The LLM judge was not exercised against live APIs here (no key available); its request, caching, retry and fallback paths are covered by tests with fake providers.
* Single-user local app: there is no authentication on the dashboard, so bind it to localhost (the default).
