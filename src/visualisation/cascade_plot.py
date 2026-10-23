"""
Plot how travel cost changes from heat to heat in a cascade scenario.

Each run releases the scenario's agents in heats (see "cascade" in config.json),
so later heats can see the edge costs earlier heats left behind. This tool runs
the scenario over several seeds and plots the average cost of each heat,
separately for every alpha group, so you can see whether (and for whom)
information about earlier heats pays off.

Usage:
    # alphas as in agents.json
    python -m src.visualisation.cascade_plot --scenario scenarios/braess_cascade

    # 30% fully informed, the rest blind
    python -m src.visualisation.cascade_plot --scenario scenarios/braess_cascade --population 1:0.3,0

    # compare whole populations: everyone blind / everyone half / everyone fully informed
    python -m src.visualisation.cascade_plot --scenario scenarios/braess_cascade \
        --population 0 --population 0.5 --population 1

Outputs (in --output, default results/<scenario>_cascade): plot.png, summary.csv, raw_results.csv.
Shaded bands are 95% confidence intervals of the mean across seeds.
"""

import argparse
import csv
import math
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from statistics import mean, stdev

from src.visualisation.populations import parse_population, run_summary


def ci95(values):
    if len(values) < 2:
        return (values[0] if values else math.nan), 0.0
    return mean(values), 1.96 * stdev(values) / math.sqrt(len(values))


def _run(task):
    label, groups, scenario, seed, max_steps = task
    return label, run_summary(scenario, groups, seed, max_steps)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--population", action="append", default=None,
                        help="Information mix, e.g. '1', '1:0.3,0'. Repeat to compare. Default: agents.json alphas.")
    parser.add_argument("--trials", type=int, default=20, help="Seeds per population")
    parser.add_argument("--seed", type=int, default=3821, help="First seed")
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--workers", type=int, default=os.cpu_count())
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--no-show", action="store_true")
    args = parser.parse_args()

    specs = args.population or [None]
    populations = [(spec, parse_population(spec)) for spec in specs]
    tasks = [
        (spec or "scenario", groups, str(args.scenario), args.seed + trial, args.max_steps)
        for spec, groups in populations for trial in range(args.trials)
    ]
    print(f"Cascade runs on {args.scenario.name}: {len(populations)} population(s) x {args.trials} seeds")

    raw = []
    incomplete = 0
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for i, (label, run) in enumerate(pool.map(_run, tasks), 1):
            incomplete += not run["completed"]
            per = {}
            for agent in run["agents"]:
                per.setdefault((agent["heat"], agent["alpha"]), []).append(agent)
                per.setdefault((agent["heat"], "all"), []).append(agent)
            for (heat, group), agents in per.items():
                raw.append({
                    "population": label, "seed": run["seed"], "heat": heat,
                    "group": group if group == "all" else f"alpha={group:g}",
                    "agents": len(agents),
                    "avg_cost": mean(a["cost"] for a in agents),
                    "avg_steps": mean(a["steps"] for a in agents if a["steps"] is not None)
                    if any(a["steps"] is not None for a in agents) else math.nan,
                    "completed": run["completed"],
                })
            if i % max(1, len(tasks) // 10) == 0 or i == len(tasks):
                print(f"  {i}/{len(tasks)} runs done", flush=True)

    if not raw:
        raise SystemExit("No agents were simulated.")
    heats = sorted({r["heat"] for r in raw})
    if len(heats) < 2:
        print("Note: this scenario has a single heat. Add e.g. "
              '"cascade": {"heats": 20, "heat_interval": 1} to its config.json.')

    summary = []
    order = [spec or "scenario" for spec in specs]
    keys = sorted({(r["population"], r["group"]) for r in raw},
                  key=lambda k: (order.index(k[0]), k[1] != "all", k[1]))
    for population, group in keys:
        for heat in heats:
            rows = [r for r in raw if r["population"] == population and r["group"] == group and r["heat"] == heat]
            if not rows:
                continue
            m, ci = ci95([r["avg_cost"] for r in rows])
            summary.append({"population": population, "group": group, "heat": heat, "runs": len(rows),
                            "mean_cost": m, "cost_ci95": ci})

    output = args.output or Path("results") / f"{args.scenario.name}_cascade"
    output.mkdir(parents=True, exist_ok=True)
    for name, rows in (("raw_results.csv", raw), ("summary.csv", summary)):
        with open(output / name, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    import matplotlib
    import matplotlib.pyplot as plt

    cmap = matplotlib.colormaps["viridis"]
    styles = ["-", "--", ":", "-."]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    labels = [spec or "scenario" for spec, _ in populations]
    for population, group in keys:
        rows = [r for r in summary if r["population"] == population and r["group"] == group]
        alpha_groups = [k for k in keys if k[0] == population and k[1] != "all"]
        if group == "all":
            if len(alpha_groups) < 2:
                continue  # one alpha group only: the 'all' line would duplicate it
            colour, label, style = "#555555", "all agents", "--"
        else:
            alpha = float(group.split("=")[1])
            colour, label = cmap(0.85 * alpha), f"α={alpha:g} agents"
            style = styles[labels.index(population) % len(styles)]
        if len(populations) > 1:
            label = f"[{population}] {label}"
        xs = [r["heat"] for r in rows]
        ys = [r["mean_cost"] for r in rows]
        ax.plot(xs, ys, marker="o", markersize=3.5, lw=1.8, color=colour, ls=style, label=label)
        ax.fill_between(xs, [y - r["cost_ci95"] for y, r in zip(ys, rows)],
                        [y + r["cost_ci95"] for y, r in zip(ys, rows)], color=colour, alpha=0.13, lw=0)

    from matplotlib.ticker import MaxNLocator
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_xlabel("heat (release order)")
    ax.set_ylabel("average travel cost per agent (time taken)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=9)
    n_heats = len(heats)
    ax.set_title(f"{args.scenario.name}: cost by heat ({n_heats} heats, {args.trials} seeds per point)", fontsize=12)
    note = "bands: 95% confidence interval across seeds"
    if incomplete:
        note += f"   warning: {incomplete} runs hit the step limit"
    fig.text(0.5, 0.01, note, ha="center", fontsize=8.5, color="#555555")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(output / "plot.png", dpi=150)
    print(f"Saved plot to {output / 'plot.png'}")
    if not args.no_show:
        plt.show()


if __name__ == "__main__":
    main()
