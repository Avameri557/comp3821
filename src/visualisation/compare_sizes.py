"""
Overlay the alpha sweeps for every population size of each network.

Reads results/<network>/summary.csv (the largest N) and results/<network>_N<n>
for the smaller sizes (N = 20 and 50, or 250 and 500 for Sioux Falls), and
writes five figures per network to results/combined/<network>/:

    cost_per_agent.png    mean social cost / N against alpha (+/- 1 std band)
    cost_vs_alpha_n.png   the same against alpha * N (expected agents observed)
    switch_rate.png       share of reviewed decisions that switched route
    max_route_share.png   share of agents on the busiest route
    route_cost_spread.png most minus least expensive used route (0 = equilibrium)

Social cost is divided by N so that different sizes share one scale.

Usage:
    python -m src.visualisation.compare_sizes
    python -m src.visualisation.compare_sizes --networks pigou braess
"""

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt

# Population sizes run for each network. The largest is the base folder.
SIZES = {
    "pigou": [20, 50, 80],
    "braess": [20, 50, 80],
    "diamond": [20, 50, 80],
    "grid": [20, 50, 80],
    "sioux_falls": [250, 500, 1000],
}
NETWORKS = list(SIZES)


def _folder(results_dir, network, n):
    """The largest N is the base folder; other sizes have an _N<n> suffix."""
    name = network if n == max(SIZES[network]) else f"{network}_N{n}"
    return Path(results_dir) / name


def _load_summary(path):
    """Read summary.csv into a list of dicts of floats."""
    with open(path, newline="") as f:
        return [
            {key: float(value) for key, value in row.items()}
            for row in csv.DictReader(f)
        ]


def _save(fig, ax, title, xlabel, ylabel, path):
    """Apply the shared labels and styling, then save and close."""
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def plot_network(network, results_dir, output_dir):
    """
    Write the five comparison figures for one network.

    Args:
        network: Base scenario name, e.g. "pigou".
        results_dir: Folder holding the per-size result folders.
        output_dir: Folder to save the figures in.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summaries = {
        n: _load_summary(_folder(results_dir, network, n) / "summary.csv")
        for n in SIZES[network]
    }
    name = network.replace("_", " ").title()

    # 1. Cost per agent against alpha, with a +/- 1 std band.
    fig, ax = plt.subplots(figsize=(9, 5))
    for n, rows in summaries.items():
        alphas = [row["alpha"] for row in rows]
        means = [row["mean_social_cost"] / n for row in rows]
        stds = [row["std_social_cost"] / n for row in rows]
        line, = ax.plot(alphas, means, label=f"N = {n}")
        ax.fill_between(
            alphas,
            [m - s for m, s in zip(means, stds)],
            [m + s for m, s in zip(means, stds)],
            color=line.get_color(),
            alpha=0.15,
        )
    _save(
        fig, ax,
        f"{name}: Social Cost per Agent by Information Level",
        "Information level (alpha)",
        "Mean social cost per agent (band: +/- 1 std)",
        output_dir / "cost_per_agent.png",
    )

    # 2. Cost per agent against alpha * N (alpha = 0 left off the log axis).
    fig, ax = plt.subplots(figsize=(9, 5))
    for n, rows in summaries.items():
        rows = [row for row in rows if row["alpha"] > 0]
        ax.plot(
            [row["alpha"] * n for row in rows],
            [row["mean_social_cost"] / n for row in rows],
            label=f"N = {n}",
        )
    ax.set_xscale("log")
    _save(
        fig, ax,
        f"{name}: Social Cost per Agent by Expected Agents Observed",
        "Expected number of other agents observed (alpha x N, log scale)",
        "Mean social cost per agent",
        output_dir / "cost_vs_alpha_n.png",
    )

    # 3-5. Route-tracking measures against alpha.
    measures = [
        ("mean_switch_rate", "switch_rate.png",
         "Route Switching by Information Level", "Mean switch rate", (0, 1.02)),
        ("mean_max_route_share", "max_route_share.png",
         "Busiest-Route Share by Information Level",
         "Mean share of agents on the busiest route", (0, 1.02)),
        ("mean_route_cost_spread", "route_cost_spread.png",
         "Route Cost Spread by Information Level",
         "Most minus least expensive used route", None),
    ]
    for column, filename, title, ylabel, ylim in measures:
        fig, ax = plt.subplots(figsize=(9, 5))
        for n, rows in summaries.items():
            ax.plot(
                [row["alpha"] for row in rows],
                [row[column] for row in rows],
                label=f"N = {n}",
            )
        if ylim:
            ax.set_ylim(*ylim)
        _save(
            fig, ax, f"{name}: {title}", "Information level (alpha)",
            ylabel, output_dir / filename,
        )


def main():
    """CLI entry point: write the comparison figures for each network."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--networks", nargs="+", default=NETWORKS)
    parser.add_argument("--results", type=Path, default=Path("results"))
    parser.add_argument(
        "--output", type=Path, default=Path("results/combined")
    )
    args = parser.parse_args()

    for network in args.networks:
        plot_network(network, args.results, args.output / network)
        print(f"Saved figures to {args.output / network}")


if __name__ == "__main__":
    main()
