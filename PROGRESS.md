# GoldenGate build progress

Only steps that are built **and** tested are checked. Weights add up to 100%.

| # | Step | Weight | Status |
|---|------|-------:|:------:|
| 1 | Corpus (40 docs), chunker, BM25/TF-IDF retrievers, demo releases 1.0–1.3 | 10 | ✅ |
| 2 | Golden v1/v2, schema, validate / diff / freeze with hash check | 8 | ✅ |
| 3 | Metrics + offline judge; planted problems verified (1.1 acc/halluc/citations, 1.2 fairness, 1.3 clean) | 12 | ✅ |
| 4 | LLM judge with rubric + caching, bootstrap CIs, fairness slices, gates | 12 | ✅ |
| 5 | SQLite storage, runner, compare, CLI (all commands, exit codes) | 8 | ✅ |
| 6 | Reports (HTML/MD/JSON/JUnit) + `pytest tests/evals` gate tests | 6 | ✅ |
| 7 | FastAPI backend (API + SPA serving + background jobs) | 5 | ✅ |
| 8 | Unit tests passing with ≥80% coverage on the core package (105 tests, 95%) | 8 | ✅ |
| 9 | React + TS + Vite + Tailwind + Recharts dashboard, built into frontend/dist | 15 | ✅ |
| 10 | GitHub Actions (PR suite + comment, baseline on main, nightly) + docs/example_pr_comment.md | 6 | ✅ |
| 11 | README + docs/ARCHITECTURE.md (Mermaid) | 4 | ✅ |
| 12 | start/run_suite scripts, .env.example, PyInstaller spec + build_exe.bat (GoldenGate.exe built and tested) | 4 | ✅ |
| 13 | Final clean-room check (fresh venv, seed, dashboard, gate exit codes) | 2 | ✅ |

**Total complete: 100%**

## Verification log (2026-11-04)
- Clean room: deleted .venv, node_modules, __pycache__, data; `start.bat` created the venv, installed, seeded 5 runs and served the dashboard (verified on port 8765 because another app holds 8000 on the build machine).
- `goldengate gate`: release_1.1 -> exit 1, release_1.2 -> exit 1, release_1.3 -> exit 0. `run_suite.bat release_1.2` -> exit 1.
- 105 unit tests pass in the fresh venv; 95% coverage of the goldengate package.
- CI flow simulated locally (baseline import, run, compare, 4 reports, pytest gates, gate exit 0).
- dist/GoldenGate.exe built with PyInstaller and tested from an empty folder (seeds and serves the dashboard).
