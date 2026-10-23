"""
Graph travel time against information.

Two experiments, both repeated over several seeds (the same seeds are used at
every x value, so differences between points are not just different draws):

1. Everyone has the same information (default)
   x-axis: alpha given to every agent
   y-axis: average travel cost per agent (the time taken), and the number of
           steps agents need to arrive

2. Mixed population (--mixed HIGH LOW)
   x-axis: share of agents that get alpha=HIGH (the rest get alpha=LOW)
   y-axis: average travel cost for each group separately, plus overall
   This shows which group has the advantage, and how it depends on how many
   others are informed.

Usage:
    python -m src.visualisation.information_plot --scenario scenarios/braess
    python -m src.visualisation.information_plot --scenario scenarios/braess --mixed 1 0
    python -m src.visualisation.information_plot --scenario scenarios/sioux_falls \
        --trials 10 --step 0.1 --output results/sioux_falls_information

Shaded bands are 95% confidence intervals of the mean across seeds.
Outputs (in --output): plot.png, summary.csv, raw_results.csv.
"""

import argparse
import csv
import math
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from statistics import mean, stdev

from src.visualisation.populations import run_summary


def grid(step):
    if not 0 < step <= 1:
        raise ValueError("--step must be in (0, 1]")
    values, i = [], 0
    while i * step < 1 - 1e-9:
        values.append(round(i * step, 10))
        i += 1
    return values + [1.0]


def ci95(values):
    """(mean, half-width of a 95% confidence interval)."""
    if not values:
        return math.nan, math.nan
    if len(values) == 1:
        return values[0], 0.0
    return mean(values), 1.96 * stdev(values) / math.sqrt(len(values))


def _run(task):
    x, groups, scenario, seed, max_steps = task
    return x, run_summary(scenario, groups, seed, max_steps)


def run_experiment(scenario, xs, make_groups, trials, base_seed, max_steps, workers):
    tasks = [
        (x, make_groups(x), str(scenario), base_seed + trial, max_steps)
        for x in xs for trial in range(trials)
    ]
    results = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i, (x, summary) in enumerate(pool.map(_run, tasks), 1):
            results.append((x, summary))
            if i % max(1, len(tasks) // 20) == 0 or i == len(tasks):
                print(f"  {i}/{len(tasks)} runs done", flush=True)
    return results


def agent_metrics(agents):
    costs = [a["cost"] for a in agents]
    steps = [a["steps"] for a in agents if a["steps"] is not None]
    return {
        "cost": mean(costs) if costs else math.nan,
        "steps": mean(steps) if steps else math.nan,
        "arrived": sum(a["arrived"] for a in agents) / len(agents) if agents else math.nan,
    }


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def summarise(results, xs, group_keys):
    """Rows of mean/CI per x and group, and raw per-run rows."""
    raw, summary = [], []
    for x, run in results:
        for key, select in group_keys:
            agents = [a for a in run["agents"] if select(a)]
            if not agents:
                continue
            m = agent_metrics(agents)
            raw.append({"x": x, "group": key, "seed": run["seed"], "completed": run["completed"],
                        "agents": len(agents), "avg_cost": m["cost"], "avg_steps": m["steps"],
                        "arrived_share": m["arrived"]})
    for x in xs:
        for key, _ in group_keys:
            rows = [r for r in raw if r["x"] == x and r["group"] == key]
            if not rows:
                continue
            cost, cost_ci = ci95([r["avg_cost"] for r in rows])
            steps_vals = [r["avg_steps"] for r in rows if not math.isnan(r["avg_steps"])]
            steps, steps_ci = ci95(steps_vals)
            summary.append({"x": x, "group": key, "runs": len(rows),
                            "incomplete_runs": sum(not r["completed"] for r in rows),
                            "mean_cost": cost, "cost_ci95": cost_ci,
                            "mean_steps": steps, "steps_ci95": steps_ci})
    return raw, summary


def plot(summary, groups, colours, xlabel, title, path, show):
    import matplotlib.pyplot as plt

    fig, (ax_cost, ax_steps) = plt.subplots(1, 2, figsize=(12, 4.8))
    any_incomplete = False
    for key, label in groups:
        rows = [r for r in summary if r["group"] == key]
        if not rows:
            continue
        xs = [r["x"] for r in rows]
        style = dict(color=colours[key], label=label)
        dashed = key == "all" and len(groups) > 1
        for ax, m, c in ((ax_cost, "mean_cost", "cost_ci95"), (ax_steps, "mean_steps", "steps_ci95")):
            ys = [r[m] for r in rows]
            lo = [r[m] - r[c] for r in rows]
            hi = [r[m] + r[c] for r in rows]
            ax.plot(xs, ys, marker="o", markersize=3.5, lw=1.8, ls="--" if dashed else "-", **style)
            ax.fill_between(xs, lo, hi, color=colours[key], alpha=0.15, lw=0)
        bad = [r for r in rows if r["incomplete_runs"]]
        if bad:
            any_incomplete = True
            ax_cost.scatter([r["x"] for r in bad], [r["mean_cost"] for r in bad], marker="x", s=60,
                            color="#c62828", zorder=5, label="some agents never arrived" if key == groups[0][0] else None)

    ax_cost.set_ylabel("average travel cost per agent (time taken)")
    ax_steps.set_ylabel("average steps to arrive")
    for ax in (ax_cost, ax_steps):
        ax.set_xlabel(xlabel)
        ax.grid(alpha=0.3)
        ax.set_xlim(-0.02, 1.02)
    ax_cost.legend(fontsize=9)
    note = "bands: 95% confidence interval across seeds"
    if any_incomplete:
        note += "   ×: some runs hit the step limit, so their costs are partial"
    fig.suptitle(title, fontsize=12)
    fig.text(0.5, 0.01, note, ha="center", fontsize=8.5, color="#555555")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(path, dpi=150)
    print(f"Saved plot to {path}")
    if show:
        plt.show()
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--mixed", nargs=2, type=float, metavar=("HIGH", "LOW"), default=None,
                        help="Mixed population: vary the share of agents with alpha=HIGH (rest alpha=LOW)")
    parser.add_argument("--trials", type=int, default=20, help="Seeds per point")
    parser.add_argument("--step", type=float, default=0.05, help="Spacing of alpha (or share) values")
    parser.add_argument("--seed", type=int, default=3821, help="First seed")
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--workers", type=int, default=os.cpu_count())
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--no-show", action="store_true")
    args = parser.parse_args()

    import matplotlib
    cmap = matplotlib.colormaps["viridis"]
    xs = grid(args.step)
    name = args.scenario.name

    if args.mixed is None:
        output = args.output or Path("results") / f"{name}_information"
        print(f"Everyone-same-alpha sweep on {name}: {len(xs)} alphas x {args.trials} seeds")
        results = run_experiment(args.scenario, xs, lambda a: [(a, 1.0)], args.trials,
                                 args.seed, args.max_steps, args.workers)
        group_keys = [("all", lambda a: True)]
        labels = [("all", "all agents")]
        colours = {"all": cmap(0.35)}
        xlabel = "information level α (same for every agent)"
        n_agents = len(results[0][1]["agents"])
        title = f"{name}: travel time vs information ({n_agents} agents, {args.trials} seeds per point)"
    else:
        high, low = args.mixed
        output = args.output or Path("results") / f"{name}_information_mixed_{high:g}_{low:g}"
        print(f"Mixed-population sweep on {name}: share with α={high:g} (rest α={low:g}), "
              f"{len(xs)} shares x {args.trials} seeds")
        results = run_experiment(args.scenario, xs, lambda s: [(high, s), (low, 1 - s)], args.trials,
                                 args.seed, args.max_steps, args.workers)
        group_keys = [("high", lambda a: a["alpha"] == high), ("low", lambda a: a["alpha"] == low),
                      ("all", lambda a: True)]
        labels = [("high", f"agents with α={high:g}"), ("low", f"agents with α={low:g}"), ("all", "all agents")]
        colours = {"high": cmap(0.85 * high), "low": cmap(0.85 * low), "all": "#555555"}
        if high == low:
            raise ValueError("--mixed needs two different alphas")
        xlabel = f"share of agents with α={high:g}"
        n_agents = len(results[0][1]["agents"])
        title = (f"{name}: who gains from information? α={high:g} vs α={low:g} "
                 f"({n_agents} agents, {args.trials} seeds per point)")

    output.mkdir(parents=True, exist_ok=True)
    raw, summary = summarise(results, xs, group_keys)
    write_csv(output / "raw_results.csv", raw)
    write_csv(output / "summary.csv", summary)
    plot(summary, labels, colours, xlabel, title, output / "plot.png", show=not args.no_show)

    incomplete = sum(r["incomplete_runs"] for r in summary if r["group"] == "all")
    if incomplete:
        print(f"Warning: {incomplete} runs hit the step limit before every agent arrived.")


if __name__ == "__main__":
    main()
