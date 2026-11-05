"""GoldenGate command-line interface (Typer + Rich)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table

from goldengate import __version__, paths
from goldengate.config import load_settings
from goldengate.gates.config import load_gates, metric_label
from goldengate.gates.engine import evaluate_gates
from goldengate.golden import store as golden
from goldengate.releases import store
from goldengate.releases.compare import compare_runs, headline_metric_names
from goldengate.releases.models import GateReport, RunRecord
from goldengate.releases.runner import run_suite
from goldengate.reports.render import EXTENSIONS, fmt_delta, fmt_metric, pct, render
from goldengate.systems.registry import SystemSpecError

app = typer.Typer(help="GoldenGate - accuracy, hallucination & bias regression suite for RAG systems.",
                  no_args_is_help=True, add_completion=False)
golden_app = typer.Typer(help="Validate, diff and freeze golden dataset versions.", no_args_is_help=True)
baseline_app = typer.Typer(help="Show, set, export or import the baseline release.", no_args_is_help=True)
app.add_typer(golden_app, name="golden")
app.add_typer(baseline_app, name="baseline")

console = Console()
EXIT_OK, EXIT_BLOCKED, EXIT_ERROR = 0, 1, 2


def _fail(message: str) -> None:
    console.print(f"[bold red]Error:[/] {message}")
    raise typer.Exit(EXIT_ERROR)


def _load(ref: str | None) -> RunRecord:
    try:
        return store.load_run(store.resolve_run(ref))
    except store.RunNotFound as exc:
        _fail(str(exc))
        raise  # unreachable, keeps type checkers happy


def _banner(report: GateReport, release: str) -> None:
    if report.verdict == "SHIP":
        console.print(Panel.fit(f"[bold white]SHIP[/]  {release} passed all {len(report.gates)} gates",
                                style="bold on green", padding=(0, 4)))
    else:
        console.print(Panel.fit(f"[bold white]BLOCKED[/]  {release} failed {len(report.failed)} of "
                                f"{len(report.gates)} gates", style="bold on red", padding=(0, 4)))
        for reason in report.reasons:
            console.print(f"  [red]•[/] {reason}")
    for warning in report.warnings:
        console.print(f"[yellow]⚠ {warning}[/]")


def _gates_table(report: GateReport) -> Table:
    table = Table(title="Release gates", header_style="bold", expand=False)
    table.add_column("Gate")
    table.add_column("Result", justify="center")
    table.add_column("Details")
    colors = {"PASS": "green", "FAIL": "red", "SKIP": "grey50"}
    for g in report.gates:
        table.add_row(g.id, f"[{colors[g.status]}]{g.status}[/]", g.message)
    return table


def _metrics_table(record: RunRecord, title: str = "Metrics") -> Table:
    table = Table(title=title, header_style="bold")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_column("95% CI", justify="right")
    table.add_column("n", justify="right")
    names = dict.fromkeys(headline_metric_names() + ["key_fact_coverage", "false_refusal_rate", "avg_answer_words"])
    for name in names:
        mv = record.metrics.get(name)
        if not mv:
            continue
        ci = f"{fmt_metric(name, mv.ci_low)} – {fmt_metric(name, mv.ci_high)}" if mv.ci_low is not None else "–"
        table.add_row(metric_label(name), fmt_metric(name, mv.value), ci, str(mv.n))
    return table


def _print_warnings(record: RunRecord) -> None:
    for warning in record.meta.warnings:
        console.print(f"[yellow]⚠ {warning}[/]")


# --------------------------------------------------------------------------- run / compare / gate


@app.command()
def run(
    system: str = typer.Option(..., "--system", "-s", help="release_1.0..1.3, llm, http:<cfg.yaml> or replay:<file.jsonl>"),
    golden_version: str = typer.Option("latest", "--golden", "-g", help="Golden version, e.g. v2"),
    judge: str = typer.Option(None, "--judge", "-j", help="auto | offline | llm (default from settings)"),
    release: str = typer.Option(None, "--release", "-r", help="Release ID to record (defaults to the system's)"),
) -> None:
    """Run the suite for one release and print metrics and the gate verdict."""
    if judge not in (None, "auto", "offline", "llm"):
        _fail("--judge must be auto, offline or llm")
    with Progress(TextColumn("[bold green]{task.description}"), BarColumn(), MofNCompleteColumn(),
                  TimeElapsedColumn(), console=console, transient=True) as bar:
        task = bar.add_task(f"Evaluating {system}", total=None)

        def progress(done: int, total: int, item_id: str) -> None:
            bar.update(task, completed=done, total=total, description=f"Evaluating {system} · {item_id}")

        try:
            record = run_suite(system, golden_version=golden_version, judge_mode=judge, release_id=release,
                               progress=progress)
        except (SystemSpecError, golden.GoldenError) as exc:
            _fail(str(exc))
            return
    meta = record.meta
    console.print(f"[bold]Run[/] {meta.run_id}  ·  release [bold]{meta.release.release_id}[/]  ·  golden "
                  f"{meta.golden_version}  ·  judge {', '.join(f'{k} ({v})' for k, v in meta.judges_used.items())}")
    _print_warnings(record)
    console.print(_metrics_table(record))
    if record.gates:
        console.print(_gates_table(record.gates))
        _banner(record.gates, meta.release.release_id)


@app.command()
def compare(
    baseline: str = typer.Option("baseline", "--baseline", "-b", help="Run ID, release ID or 'baseline'"),
    current: str = typer.Option("latest", "--current", "-c", help="Run ID, release ID or 'latest'"),
) -> None:
    """Compare a release with the baseline: metric deltas with CIs, newly failing items, slices."""
    base, cur = _load(baseline), _load(current)
    result = compare_runs(base, cur, samples=load_settings().bootstrap_samples)
    console.print(f"[bold]{result.current_release}[/] ({result.current_run_id}) vs baseline "
                  f"[bold]{result.baseline_release}[/] ({result.baseline_run_id}) · {result.common_items} shared items")
    for warning in result.warnings:
        console.print(f"[yellow]⚠ {warning}[/]")
    table = Table(title="Metric deltas", header_style="bold")
    for col, justify in (("Metric", "left"), ("Baseline", "right"), ("Current", "right"), ("Δ (95% CI)", "right"),
                         ("", "center")):
        table.add_column(col, justify=justify)  # type: ignore[arg-type]
    shown = set(headline_metric_names())
    for d in result.metrics:
        if d.name not in shown:
            continue
        worse = d.delta is not None and ((d.delta < 0) if d.higher_is_better else (d.delta > 0))
        color = "red" if worse and (d.significant or d.regression) else ("green" if d.delta and not worse else "white")
        flag = "[red]▼ regression[/]" if d.regression else ("[green]▲[/]" if d.delta and not worse and d.significant else "")
        table.add_row(d.label, fmt_metric(d.name, d.baseline), fmt_metric(d.name, d.current),
                      f"[{color}]{fmt_delta(d.name, d.delta, d.delta_ci_low, d.delta_ci_high)}[/]", flag)
    console.print(table)
    if result.newly_failing:
        items = Table(title=f"Newly failing items ({len(result.newly_failing)})", header_style="bold")
        items.add_column("Item")
        items.add_column("Critical", justify="center")
        items.add_column("Why")
        for change in result.newly_failing[:15]:
            items.add_row(change.item_id, "[red]yes[/]" if change.critical else "", "; ".join(change.reasons[:2]))
        console.print(items)
    if result.slice_changes:
        slices = Table(title="Largest per-slice changes", header_style="bold")
        for col in ("Dimension", "Slice", "Metric", "Baseline", "Current", "Δ"):
            slices.add_column(col)
        for s in result.slice_changes[:8]:
            slices.add_row(s.dimension, s.value, s.metric, pct(s.baseline), pct(s.current), fmt_delta(s.metric, s.delta))
        console.print(slices)
    console.print(_gates_table(result.gates))
    _banner(result.gates, result.current_release)


@app.command()
def gate(
    run_ref: str = typer.Option("latest", "--run", help="Run ID, release ID or 'latest'"),
    baseline: str = typer.Option(None, "--baseline", "-b", help="Override the baseline (run or release ID)"),
) -> None:
    """Evaluate release gates. Exit code 0 = SHIP, 1 = BLOCKED, 2 = error."""
    record = _load(run_ref)
    base = _load(baseline) if baseline else store.baseline_run()
    report = evaluate_gates(load_gates(), record, base)
    console.print(f"[bold]Gates for[/] {record.meta.run_id} (baseline: "
                  f"{base.meta.release.release_id if base else 'none'})")
    console.print(_gates_table(report))
    _banner(report, record.meta.release.release_id)
    raise typer.Exit(EXIT_OK if report.verdict == "SHIP" else EXIT_BLOCKED)


@app.command()
def slices(run_ref: str = typer.Option("latest", "--run", help="Run ID, release ID or 'latest'")) -> None:
    """Show fairness slices, gaps with significance and counterfactual consistency."""
    record = _load(run_ref)
    f = record.fairness
    table = Table(title=f"Fairness slices · {record.meta.run_id}", header_style="bold")
    for col in ("Dimension", "Slice", "n", "Accuracy", "Hallucination", "Refusal", "Helpfulness", "Words"):
        table.add_column(col, justify="left" if col in ("Dimension", "Slice") else "right")
    for s in f.slices:
        m = s.metrics
        table.add_row(s.dimension, s.value + (" [yellow](small)[/]" if s.below_min_size else ""), str(s.n),
                      pct(m["accuracy"]), pct(m["hallucination_rate"]), pct(m["refusal_rate"]),
                      pct(m["helpfulness"]), f"{m['answer_words']:.1f}")
    console.print(table)
    gaps = Table(title="Max gap per dimension and metric", header_style="bold")
    for col in ("Dimension", "Metric", "Best", "Worst", "Gap", "95% CI", "p", "Flag"):
        gaps.add_column(col)
    for g in f.gaps:
        if g.metric == "answer_words":
            continue
        gaps.add_row(g.dimension, g.metric, f"{g.best_value} {pct(g.best)}", f"{g.worst_value} {pct(g.worst)}",
                     pct(g.gap), f"{pct(g.ci_low)}–{pct(g.ci_high)}",
                     "–" if g.p_value is None else f"{g.p_value:.3f}", "[red]FLAG[/]" if g.flagged else "")
    console.print(gaps)
    console.print(f"Counterfactual consistency: [bold]{pct(f.counterfactual_consistency)}[/] of {len(f.groups)} "
                  f"groups · pair consistency {pct(f.pair_consistency)}")
    for g in [g for g in f.groups if not g.consistent][:8]:
        console.print(f"  [red]•[/] {g.group}: {'; '.join(g.differences)}")


@app.command()
def report(
    run_ref: str = typer.Option("latest", "--run", help="Run ID, release ID or 'latest'"),
    fmt: str = typer.Option("html", "--format", "-f", help="html | md | json | junit"),
    output: Path = typer.Option(None, "--output", "-o", help="Output file (default data/reports/<run>.<ext>)"),
    baseline: str = typer.Option("baseline", "--baseline", "-b", help="Baseline run/release, or 'none'"),
) -> None:
    """Write a release report (HTML for managers, Markdown for PR comments, JSON, JUnit XML)."""
    if fmt not in EXTENSIONS:
        _fail(f"--format must be one of {', '.join(EXTENSIONS)}")
    record = _load(run_ref)
    base = None
    if baseline != "none":
        try:
            base = store.load_run(store.resolve_run(baseline))
        except store.RunNotFound:
            console.print("[yellow]⚠ No baseline found; reporting without comparison.[/]")
    text = render(fmt, record, base)
    target = output or paths.reports_dir() / f"{record.meta.run_id}.{EXTENSIONS[fmt]}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    console.print(f"[green]Wrote[/] {target}")


# --------------------------------------------------------------------------- golden


@golden_app.command("list")
def golden_list() -> None:
    """List golden versions with item counts and freeze status."""
    table = Table(header_style="bold")
    for col in ("Version", "Created", "Items", "Frozen", "Hash", "Description"):
        table.add_column(col)
    for v in golden.list_versions():
        m = golden.load_manifest(v)
        table.add_row(v, m.created, str(m.item_count), "yes" if m.frozen else "no", m.content_hash[:12], m.description)
    console.print(table)


@golden_app.command("validate")
def golden_validate(version: str = typer.Argument("all", help="Version to validate, or 'all'")) -> None:
    """Validate schema, content hash (frozen versions), IDs and gold chunk references."""
    versions = golden.list_versions() if version == "all" else [golden.resolve_version(version)]
    ok = True
    for v in versions:
        result = golden.validate(v)
        status = "[green]valid[/]" if result.ok else "[red]INVALID[/]"
        console.print(f"{v}: {status} · {result.item_count} items")
        for err in result.errors:
            console.print(f"   [red]✗[/] {err}")
        for warn in result.warnings:
            console.print(f"   [yellow]⚠[/] {warn}")
        ok = ok and result.ok
    raise typer.Exit(EXIT_OK if ok else EXIT_BLOCKED)


@golden_app.command("diff")
def golden_diff(a: str = typer.Argument(..., help="Older version"), b: str = typer.Argument(..., help="Newer version")) -> None:
    """Show items added, removed and changed between two golden versions."""
    try:
        d = golden.diff(golden.resolve_version(a), golden.resolve_version(b))
    except golden.GoldenError as exc:
        _fail(str(exc))
        return
    console.print(f"[bold]{d.a} → {d.b}[/]: [green]+{len(d.added)} added[/], [red]-{len(d.removed)} removed[/], "
                  f"[yellow]~{len(d.changed)} changed[/], {d.unchanged} unchanged")
    if d.changed:
        table = Table(title="Changed items", header_style="bold")
        table.add_column("Item")
        table.add_column("Field")
        table.add_column("Before")
        table.add_column("After")
        for item_id, fields in d.changed.items():
            for field in fields:
                det = d.details[item_id][field]
                table.add_row(item_id, field, str(det["before"])[:70], str(det["after"])[:70])
        console.print(table)
    if d.added:
        console.print("[green]Added:[/] " + ", ".join(d.added[:30]) + (" …" if len(d.added) > 30 else ""))
    if d.removed:
        console.print("[red]Removed:[/] " + ", ".join(d.removed))
    for line in golden.load_manifest(d.b).changelog:
        console.print(f"  [dim]changelog:[/] {line}")


@golden_app.command("freeze")
def golden_freeze(version: str = typer.Argument(..., help="Version to freeze")) -> None:
    """Record the content hash and mark a version frozen (edits will then fail validation)."""
    try:
        manifest = golden.freeze(golden.resolve_version(version))
    except golden.GoldenError as exc:
        _fail(str(exc))
        return
    console.print(f"[green]Frozen[/] {manifest.version} · {manifest.item_count} items · hash {manifest.content_hash[:16]}")


# --------------------------------------------------------------------------- baseline


@baseline_app.command("set")
def baseline_set(release: str = typer.Option(..., "--release", "-r", help="Release ID to use as baseline")) -> None:
    """Make a release (its latest run) the baseline for comparisons and delta gates."""
    try:
        store.set_baseline(release)
    except store.RunNotFound as exc:
        _fail(str(exc))
    console.print(f"[green]Baseline set to[/] {release} (run {store.latest_run_id(release)})")


@baseline_app.command("show")
def baseline_show() -> None:
    """Print the current baseline release and run."""
    release = store.get_baseline()
    if not release:
        console.print("No baseline set.")
        raise typer.Exit(EXIT_ERROR)
    console.print(f"Baseline: [bold]{release}[/] (run {store.latest_run_id(release)})")


@baseline_app.command("export")
def baseline_export(path: Path = typer.Argument(paths.baselines_dir() / "baseline.json")) -> None:
    """Export the baseline run JSON (committed to the repo for CI)."""
    release = store.get_baseline()
    run_id = store.latest_run_id(release) if release else None
    if not run_id:
        _fail("No baseline set")
        return
    store.export_run(run_id, path)
    console.print(f"[green]Exported[/] {run_id} → {path}")


@baseline_app.command("import")
def baseline_import(path: Path = typer.Argument(paths.baselines_dir() / "baseline.json")) -> None:
    """Import a baseline run JSON (e.g. in CI) and make its release the baseline."""
    if not path.exists():
        _fail(f"{path} not found")
    record = store.import_run(path)
    console.print(f"[green]Imported baseline[/] {record.meta.release.release_id} ({record.meta.run_id})")


# --------------------------------------------------------------------------- demo / serve


@app.command()
def demo(reset: bool = typer.Option(False, "--reset", help="Delete existing runs before seeding")) -> None:
    """Seed corpus, golden v1+v2 and all four demo releases; set release_1.0 as baseline."""
    from goldengate.demo import seed_demo

    if store.has_data() and not reset:
        console.print("Demo data already present (use --reset to re-seed).")
    else:
        seed_demo(reset=reset, on_step=lambda i, n, label: console.print(f"[{i}/{n}] running {label} …"))
    table = Table(title="Releases", header_style="bold")
    table.add_column("Release", no_wrap=True)
    for col in ("Golden", "Accuracy", "Hallucination", "Citation precision", "Max slice gap", "Verdict"):
        table.add_column(col)
    from goldengate.releases.history import release_history

    for row in release_history():
        m = row["metrics"]
        verdict = row["verdict"]
        table.add_row(str(row["release_id"]) + (" (baseline)" if row["is_baseline"] else ""), str(row["golden_version"]),
                      pct(m.get("accuracy")), pct(m.get("hallucination_rate")), pct(m.get("citation_precision")),
                      pct(m.get("max_slice_gap")),
                      f"[{'green' if verdict == 'SHIP' else 'red'}]{verdict}[/]")
    console.print(table)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind address"),
    port: int = typer.Option(8000, help="Port"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open the dashboard in a browser"),
    seed: bool = typer.Option(True, "--seed/--no-seed", help="Seed demo data on first launch"),
) -> None:
    """Start the dashboard at http://localhost:8000 (API + built React app)."""
    from goldengate.server.launcher import launch

    launch(host=host, port=port, open_browser=open_browser, seed=seed)


@app.command()
def version() -> None:
    """Print the GoldenGate version."""
    console.print(f"goldengate {__version__}")


if __name__ == "__main__":
    app()
