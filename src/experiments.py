"""
The four tests, run on every network, with one chart per network per test.

    symmetric             every agent has the same alpha, swept from 0 to 1
    others_rising         one random agent (the "informed agent") is held at
                          alpha = 1 while every other agent's alpha is swept from 0 to 1
    informed_rising       every other agent is held at alpha = 0 while the
                          informed agent's alpha is swept from 0 to 1
    informed_rising_half  every other agent is held at alpha = 0.5 while the
                          informed agent's alpha is swept from 0 to 1

Each point is the mean over --trials trials (default 200). Trial t uses seed
3821 + t at every alpha, so the points along a line differ only in
information. The informed agent is a random agent in each trial (the same
agent at every alpha).

Charts show the mean cost per agent (all agents), the informed agent's cost
(informed-agent tests only), each with a shaded 95% confidence band, and, for
reference, the Wardrop equilibrium and social optimum cost per agent from
src.benchmarks.frank_wolfe.

Usage:
    python -m src.experiments                                  # everything
    python -m src.experiments --network pigou --test symmetric
    python -m src.experiments --plot-only                      # redraw charts from the CSVs

Outputs:
    results/benchmarks.csv
    results/<network>/<test>.csv and <test>.png
"""

import argparse
import csv
import math
import os
import random
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from statistics import mean, stdev

from src.benchmarks.frank_wolfe import solve_scenario
from src.simulation.scenario_loader import load_scenario

NETWORKS = {
    "pigou": "Pigou",
    "braess": "Braess",
    "diamond": "Diamond",
    "grid": "Grid",
    "sioux_falls": "Sioux Falls",
}
TESTS = ("symmetric", "others_rising", "informed_rising", "informed_rising_half")
# Fixed alpha of the other agents in the tests that sweep the informed agent.
OTHERS_ALPHA = {"informed_rising": 0.0, "informed_rising_half": 0.5}
SCENARIOS = Path("scenarios")
RESULTS = Path("results")
BASE_SEED = 3821


# --------------------------------------------------------------------------- running

def alpha_grid(step):
    n = round(1 / step)
    if not math.isclose(n * step, 1):
        raise ValueError("--step must divide 1 exactly (e.g. 0.05, 0.1)")
    return [round(i * step, 10) for i in range(n + 1)]


def run_one(scenario, seed, test, alpha):
    """One simulation. Returns (completed, mean cost per agent, informed agent's cost)."""
    simulation, config = load_scenario(scenario, seed=seed)
    agents = simulation.agents
    # Separate random stream, so picking the agent does not change the simulation's draws.
    informed = random.Random(seed * 7919 + 1).choice(agents)
    for agent in agents:
        if test == "symmetric":
            agent.alpha = alpha
        elif test == "others_rising":
            agent.alpha = 1.0 if agent is informed else alpha
        else:  # informed_rising, informed_rising_half
            agent.alpha = alpha if agent is informed else OTHERS_ALPHA[test]
    result = simulation.run_until_complete(config.get("max_timesteps", 100))
    return result["completed"], result["average_cost"], informed.total_cost


def run_trial(task):
    """All alphas for one trial (one seed)."""
    scenario, test, seed, alphas = task
    return [(alpha, *run_one(scenario, seed, test, alpha)) for alpha in alphas]


def ci95(values):
    return 1.96 * stdev(values) / math.sqrt(len(values)) if len(values) > 1 else 0.0


def run_test(network, test, trials, alphas, benchmark, workers):
    tasks = [(str(SCENARIOS / network), test, BASE_SEED + t, alphas) for t in range(trials)]
    runs = {alpha: [] for alpha in alphas}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for trial in pool.map(run_trial, tasks, chunksize=max(1, trials // (4 * (workers or 1)))):
            for alpha, completed, avg, informed in trial:
                runs[alpha].append((completed, avg, informed))

    rows = []
    for alpha in alphas:
        completed, avg, informed = zip(*runs[alpha])
        row = {
            "alpha": alpha,
            "runs": len(avg),
            "incomplete_runs": len(avg) - sum(completed),
            "mean_cost_per_agent": mean(avg),
            "mean_cost_per_agent_ci95": ci95(avg),
        }
        if test != "symmetric":
            row["informed_agent_cost"] = mean(informed)
            row["informed_agent_cost_ci95"] = ci95(informed)
        row["wardrop_per_agent"] = benchmark["wardrop_per_agent"]
        row["optimum_per_agent"] = benchmark["optimum_per_agent"]
        rows.append(row)
    return rows


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with path.open(encoding="utf-8") as f:
        return [{k: float(v) for k, v in row.items()} for row in csv.DictReader(f)]


def benchmarks(networks):
    rows = []
    for network in networks:
        result = solve_scenario(SCENARIOS / network)
        agents = result["agents"]
        rows.append({
            "network": network,
            "agents": agents,
            "wardrop_per_agent": result["wardrop_equilibrium"]["total_cost"] / agents,
            "optimum_per_agent": result["social_optimum"]["total_cost"] / agents,
            "price_of_anarchy": result["price_of_anarchy"],
        })
    return rows


# --------------------------------------------------------------------------- charts

COLOURS = {"mean": "#1f4e79", "informed": "#c62828", "wardrop": "#666666", "optimum": "#000000"}
X_LABELS = {
    "symmetric": r"$\alpha$ of every agent",
    "others_rising": r"$\alpha$ of the other agents",
    "informed_rising": r"$\alpha$ of the informed agent",
    "informed_rising_half": r"$\alpha$ of the informed agent",
}
INFORMED_LABELS = {
    "others_rising": r"Informed agent ($\alpha = 1$)",
    "informed_rising": "Informed agent (others at $\\alpha = 0$)",
    "informed_rising_half": "Informed agent (others at $\\alpha = 0.5$)",
}


def chart_style():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["cmr10", "DejaVu Serif"],
        "mathtext.fontset": "cm",
        "axes.formatter.use_mathtext": True,
        "axes.unicode_minus": False,
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.labelsize": 11,
        "legend.fontsize": 9.5,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "savefig.dpi": 200,
    })
    return plt


def plot_network(network, results_dir):
    """One chart per test for a network, each with its y-axis fitted to its own data."""
    plt = chart_style()
    data = {test: read_csv(results_dir / network / f"{test}.csv")
            for test in TESTS if (results_dir / network / f"{test}.csv").exists()}
    if not data:
        return []
    def y_range(rows):
        """Fit the y-axis to this chart's lines, bands and benchmark lines, plus a small margin."""
        values = []
        for row in rows:
            values += [row["wardrop_per_agent"], row["optimum_per_agent"]]
            for key in ("mean_cost_per_agent", "informed_agent_cost"):
                if key in row:
                    values += [row[key] - row[f"{key}_ci95"], row[key] + row[f"{key}_ci95"]]
        low, high = min(values), max(values)
        pad = 0.06 * (high - low) if high > low else 0.05 * (abs(high) or 1)
        return low - pad, high + pad

    def line(ax, xs, rows, key, colour, marker, label):
        """Mean with a shaded 95% confidence band."""
        ys = [row[key] for row in rows]
        ci = [row[f"{key}_ci95"] for row in rows]
        ax.fill_between(xs, [y - c for y, c in zip(ys, ci)], [y + c for y, c in zip(ys, ci)],
                        color=colour, alpha=0.18, lw=0, zorder=2)
        ax.plot(xs, ys, color=colour, lw=1.8, marker=marker, ms=3, label=label, zorder=3)

    paths = []
    for test, rows in data.items():
        xs = [row["alpha"] for row in rows]
        fig, ax = plt.subplots(figsize=(6, 4.4))
        line(ax, xs, rows, "mean_cost_per_agent", COLOURS["mean"], "o", "Mean cost per agent")
        if test != "symmetric":
            line(ax, xs, rows, "informed_agent_cost", COLOURS["informed"], "s", INFORMED_LABELS[test])
        ax.axhline(rows[0]["wardrop_per_agent"], color=COLOURS["wardrop"], ls="--", lw=1.2,
                   label="Wardrop equilibrium", zorder=2)
        ax.axhline(rows[0]["optimum_per_agent"], color=COLOURS["optimum"], ls=":", lw=1.4,
                   label="Social optimum", zorder=2)
        ax.set_xlim(-0.02, 1.02)
        ax.set_ylim(*y_range(rows))
        ax.set_xlabel(X_LABELS[test])
        ax.set_ylabel("Mean cost per agent")
        ax.set_title(NETWORKS[network])
        entries = len(ax.get_legend_handles_labels()[0])
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=3 if entries == 3 else 2, frameon=False)
        fig.tight_layout()
        path = results_dir / network / f"{test}.png"
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        paths.append(path)
    return paths


# --------------------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--network", action="append", choices=list(NETWORKS),
                        help="Network to run (repeatable). Default: all")
    parser.add_argument("--test", action="append", choices=TESTS, help="Test to run (repeatable). Default: all")
    parser.add_argument("--step", type=float, default=0.05, help="Spacing of the alpha values")
    parser.add_argument("--trials", type=int, default=200, help="Trials per point")
    parser.add_argument("--workers", type=int, default=os.cpu_count())
    parser.add_argument("--output", type=Path, default=RESULTS)
    parser.add_argument("--plot-only", action="store_true", help="Redraw the charts from existing CSVs")
    args = parser.parse_args()

    networks = args.network or list(NETWORKS)
    tests = args.test or list(TESTS)

    if not args.plot_only:
        bench = benchmarks(networks)
        bench_path = args.output / "benchmarks.csv"
        existing = [r for r in (read_bench(bench_path) if bench_path.exists() else []) if r["network"] not in networks]
        write_csv(bench_path, sorted(existing + bench, key=lambda r: list(NETWORKS).index(r["network"])))
        alphas = alpha_grid(args.step)
        for row in bench:
            network = row["network"]
            for test in tests:
                print(f"{network} / {test}: {args.trials} trials x {len(alphas)} alphas", flush=True)
                rows = run_test(network, test, args.trials, alphas, row, args.workers)
                write_csv(args.output / network / f"{test}.csv", rows)
                incomplete = sum(r["incomplete_runs"] for r in rows)
                if incomplete:
                    print(f"  warning: {incomplete} runs hit max_timesteps before every agent arrived")

    for network in networks:
        for path in plot_network(network, args.output):
            print(f"Saved {path}")


def read_bench(path):
    with path.open(encoding="utf-8") as f:
        return [{k: (v if k == "network" else float(v)) for k, v in row.items()} for row in csv.DictReader(f)]


if __name__ == "__main__":
    main()
