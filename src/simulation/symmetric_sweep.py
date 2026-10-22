"""
Run a controlled alpha sweep over an existing scenario.

Usage:
    python -m src.simulation.symmetric_sweep \
        --scenario scenarios/generated \
        --output results/alpha_sweep \
        --trials 30 \
        --alpha-step 0.05
"""

import argparse
import csv

from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, stdev

import matplotlib.pyplot as plt

from src.simulation.scenario_loader import load_scenario



def _route_label(route):
    return "-".join(str(node) for node in route)



def _build_alphas(alpha_step):
    if not 0 < alpha_step <= 1:
        raise ValueError("alpha_step must be in (0, 1]")

    # Include both endpoints, even if the step
    # does not divide 1 exactly.
    alphas = []
    i = 0
    while i * alpha_step < 1 - 1e-10:
        alphas.append(round(i * alpha_step, 10))
        i += 1
    alphas.append(1.0)

    return alphas



def _write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(rows[0].keys()),
        )
        writer.writeheader()
        writer.writerows(rows)



def _summarise(rows, alphas):
    """Aggregate per-run rows into one summary row per alpha."""
    summary = []

    for alpha in alphas:
        matching = [
            row for row in rows
            if row["alpha"] == alpha
        ]

        costs = [
            row["social_cost"]
            for row in matching
        ]

        summary.append({
            "alpha": alpha,
            "trials": len(costs),
            "mean_social_cost": mean(costs),
            "std_social_cost": (
                stdev(costs) if len(costs) > 1 else 0.0
            ),
            "min_social_cost": min(costs),
            "max_social_cost": max(costs),
            "mean_timesteps": mean(
                row["timesteps"] for row in matching
            ),
            "mean_switch_rate": mean(
                row["switch_rate"] for row in matching
            ),
            "mean_max_route_share": mean(
                row["max_route_share"] for row in matching
            ),
            "mean_route_cost_spread": mean(
                row["route_cost_spread"] for row in matching
            ),
        })

    return summary



def _run_and_track(simulation, max_steps):
    """
    Run a simulation to completion while tallying
    reassessment switches and per-edge loads.

    Edge flows are reset every timestep, so loads
    are summed across steps rather than read at the end.
    """
    switches = 0
    reviewed = 0
    intended_loads = Counter()
    realised_loads = Counter()

    for snapshot in simulation.run(max_steps=max_steps):
        for decision in snapshot["decisions"]:
            reviewed += decision["review_eligible"]
            switches += decision["reassessed"]
        intended_loads.update(snapshot["initial_flows"])
        realised_loads.update(snapshot["new_flows"])

    return (
        simulation.results(),
        switches,
        reviewed,
        intended_loads,
        realised_loads,
    )



def run_alpha_sweep(
    scenario_dir,
    output_dir,
    trials=30,
    alpha_step=0.05,
    base_seed=3821,
):
    """
    Run every (trial, alpha) combination on a scenario and
    save the results as CSVs.

    Every agent in a run is given the same alpha. Trial t
    uses seed base_seed + t for all alphas, so alphas within
    a trial share the same agents and randomness source.

    Args:
        scenario_dir: Scenario folder (see load_scenario).
        output_dir: Where the CSVs are written. Created if
            missing. raw_results.csv has one row per run,
            route_results.csv one row per (run, route taken),
            edge_results.csv one row per (run, edge), and
            summary.csv one row per alpha.
        trials: Number of seeds to repeat each alpha with.
        alpha_step: Spacing between alphas in [0, 1]; 0 and 1
            are always included.
        base_seed: Seed for trial 0.

    Returns:
        (summary, route_rows): the rows written to summary.csv
        and route_results.csv.

    Raises:
        ValueError: If trials < 1 or alpha_step is not in (0, 1].
        RuntimeError: If a run hits max_timesteps before every
            agent arrives.
    """
    scenario_dir = Path(scenario_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if trials < 1:
        raise ValueError("trials must be at least 1")

    alphas = _build_alphas(alpha_step)

    rows = []
    route_rows = []
    edge_rows = []

    for trial in range(trials):
        seed = base_seed + trial

        for alpha in alphas:
            # Reload from scratch for every run. We only
            # need final results, not the full history.
            simulation, config = load_scenario(
                scenario_dir,
                {"seed": seed, "record_history": False},
            )

            # Assign the same information level
            # to every agent in this simulation.
            for agent in simulation.agents:
                agent.alpha = alpha

            (
                result,
                switches,
                reviewed,
                intended_loads,
                realised_loads,
            ) = _run_and_track(
                simulation,
                config.get("max_timesteps", 10000),
            )

            if not result["completed"]:
                raise RuntimeError(
                    f"Simulation incomplete: "
                    f"trial={trial}, alpha={alpha}, "
                    f"arrived={result['arrived_count']}/"
                    f"{result['agent_count']}"
                )

            # Group agents by the full path they took.
            route_costs = defaultdict(list)
            for agent in result["agents"]:
                route_costs[_route_label(agent["route"])].append(
                    agent["cost"]
                )

            agent_count = result["agent_count"]
            mean_route_costs = [
                mean(costs) for costs in route_costs.values()
            ]

            rows.append({
                "trial": trial,
                "seed": seed,
                "alpha": alpha,
                "social_cost": result["total_cost"],
                "average_agent_cost": result["average_cost"],
                "timesteps": result["timesteps"],
                "agent_count": agent_count,
                "switches": switches,
                "reviewed": reviewed,
                "switch_rate": (
                    switches / reviewed if reviewed else 0.0
                ),
                "routes_used": len(route_costs),
                "max_route_share": max(
                    len(costs) for costs in route_costs.values()
                ) / agent_count,
                # Near zero means every used route cost the
                # same, i.e. the split is close to equilibrium.
                "route_cost_spread": (
                    max(mean_route_costs) - min(mean_route_costs)
                ),
            })

            for route, costs in sorted(route_costs.items()):
                route_rows.append({
                    "trial": trial,
                    "seed": seed,
                    "alpha": alpha,
                    "route": route,
                    "agents": len(costs),
                    "share": len(costs) / agent_count,
                    "mean_agent_cost": mean(costs),
                })

            # Include unused edges so every run has
            # the same set of rows.
            for u, v in simulation.network.graph.edges():
                edge_rows.append({
                    "trial": trial,
                    "seed": seed,
                    "alpha": alpha,
                    "source": u,
                    "target": v,
                    "intended_load": intended_loads[(u, v)],
                    "realised_load": realised_loads[(u, v)],
                })

            print(
                f"Trial {trial + 1}/{trials} | "
                f"alpha={alpha:.2f} | "
                f"cost={result['total_cost']:.4f} | "
                f"switches={switches}"
            )

    # Save every individual simulation.
    _write_csv(output_dir / "raw_results.csv", rows)
    _write_csv(output_dir / "route_results.csv", route_rows)
    _write_csv(output_dir / "edge_results.csv", edge_rows)

    
    summary = _summarise(rows, alphas)
    _write_csv(output_dir / "summary.csv", summary)

    return summary, route_rows



def plot_results(summary, output_dir):
    """
    Plot mean social cost against alpha, with a +/- 1 standard
    deviation band, and save it as alpha_sweep.png.

    Args:
        summary: Rows returned by run_alpha_sweep.
        output_dir: Folder to save the figure in.
    """
    alphas = [row["alpha"] for row in summary]
    means = [row["mean_social_cost"] for row in summary]
    stds = [row["std_social_cost"] for row in summary]

    lower = [
        max(0, m - s) for m, s in zip(means, stds)
    ]
    upper = [
        m + s for m, s in zip(means, stds)
    ]

    plt.figure(figsize=(9, 5))

    plt.plot(
        alphas,
        means,
        marker="o",
        label="Mean social cost",
    )

    plt.fill_between(
        alphas,
        lower,
        upper,
        alpha=0.2,
        label="Mean +/- 1 standard deviation",
    )

    plt.xlabel("Information level (alpha)")
    plt.ylabel("Total social cost")
    plt.title("Effect of Information on Social Cost")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()

    plt.savefig(
        Path(output_dir) / "alpha_sweep.png",
        dpi=200,
    )
    plt.close()



def plot_routes(summary, route_rows, output_dir):
    """
    Plot the mean share of agents on each route against alpha,
    with the mean switch rate on a second axis, and save it as
    alpha_routes.png.

    Args:
        summary: Summary rows returned by run_alpha_sweep.
        route_rows: Route rows returned by run_alpha_sweep.
        output_dir: Folder to save the figure in.
    """
    alphas = [row["alpha"] for row in summary]
    trials_per_alpha = {
        row["alpha"]: row["trials"] for row in summary
    }
    switch_rates = [row["mean_switch_rate"] for row in summary]

    # share_sums[route][alpha] = total share of agents on
    # that route, added up over every trial at that alpha.
    share_sums = defaultdict(lambda: defaultdict(float))
    for row in route_rows:
        share_sums[row["route"]][row["alpha"]] += row["share"]

    fig, share_axis = plt.subplots(figsize=(9, 5))

    for route in sorted(share_sums):
        # Divide by every trial, not just the trials that
        # used this route, so an unused route counts as 0.
        mean_shares = [
            share_sums[route][alpha] / trials_per_alpha[alpha]
            for alpha in alphas
        ]
        share_axis.plot(
            alphas,
            mean_shares,
            label=f"Route {route}",
        )

    # Second y-axis on the right for the switch rate.
    switch_axis = share_axis.twinx()
    switch_axis.plot(
        alphas,
        switch_rates,
        color="black",
        linestyle="--",
        label="Switch rate",
    )

    share_axis.set_xlabel("Information level (alpha)")
    share_axis.set_ylabel("Mean share of agents")
    share_axis.set_ylim(0, 1)
    switch_axis.set_ylabel("Mean switch rate")
    switch_axis.set_ylim(0, 1)
    share_axis.set_title(
        "Route Choice and Switching by Information Level"
    )
    share_axis.grid(True, alpha=0.3)

    # Each axis keeps its own legend entries, so
    # combine them into a single legend.
    route_lines, route_labels = (
        share_axis.get_legend_handles_labels()
    )
    switch_lines, switch_labels = (
        switch_axis.get_legend_handles_labels()
    )
    share_axis.legend(
        route_lines + switch_lines,
        route_labels + switch_labels,
    )

    fig.tight_layout()
    fig.savefig(
        Path(output_dir) / "alpha_routes.png",
        dpi=200,
    )
    plt.close(fig)



def main():
    """CLI entry point: run the sweep, plot it and report the best alpha."""
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--scenario",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/alpha_sweep"),
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=30,
    )
    parser.add_argument(
        "--alpha-step",
        type=float,
        default=0.05,
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=3821,
    )

    args = parser.parse_args()

    summary, route_rows = run_alpha_sweep(
        scenario_dir=args.scenario,
        output_dir=args.output,
        trials=args.trials,
        alpha_step=args.alpha_step,
        base_seed=args.seed,
    )

    plot_results(summary, args.output)
    plot_routes(summary, route_rows, args.output)

    print("\nAlpha sweep complete.")
    print(f"Results saved to: {args.output}")

    best = min(
        summary,
        key=lambda row: row["mean_social_cost"],
    )

    print(
        f"Lowest mean social cost: "
        f"alpha={best['alpha']:.2f}, "
        f"cost={best['mean_social_cost']:.4f}"
    )



if __name__ == "__main__":
    main()
