
"""
Run a controlled alpha sweep over an existing scenario.

Usage:
    python -m src.simulation.alpha_sweep \
        --scenario scenarios/generated \
        --output results/alpha_sweep \
        --trials 30 \
        --alpha-step 0.05
"""

import argparse
import csv
import json
import shutil
import tempfile

from pathlib import Path
from statistics import mean, stdev

from src.simulation.scenario_loader import load_scenario


def run_alpha_sweep(
    scenario_dir,
    output_dir,
    trials=30,
    alpha_step=0.05,
    base_seed=3821,
):
    scenario_dir = Path(scenario_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if trials < 1:
        raise ValueError("trials must be at least 1")

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

    config_path = scenario_dir / "config.json"

    config = (
        json.loads(config_path.read_text(encoding="utf-8"))
        if config_path.exists()
        else {}
    )

    max_steps = config.get("max_timesteps", 10000)

    rows = []

    # A temporary scenario allows each trial to use
    # a different seed without changing user files.
    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)

        shutil.copy2(
            scenario_dir / "network.json",
            temp_dir / "network.json",
        )
        shutil.copy2(
            scenario_dir / "agents.json",
            temp_dir / "agents.json",
        )

        for trial in range(trials):
            seed = base_seed + trial

            trial_config = dict(config)
            trial_config["seed"] = seed

            # We only need final results, not the
            # full timestep history.
            trial_config["record_history"] = False

            (temp_dir / "config.json").write_text(
                json.dumps(trial_config),
                encoding="utf-8",
            )

            for alpha in alphas:
                # Reload from scratch for every run.
                simulation, _ = load_scenario(temp_dir)

                # Assign the same information level
                # to every agent in this simulation.
                for agent in simulation.agents:
                    agent.alpha = alpha

                result = simulation.run_until_complete(
                    max_steps=max_steps
                )

                if not result["completed"]:
                    raise RuntimeError(
                        f"Simulation incomplete: "
                        f"trial={trial}, alpha={alpha}, "
                        f"arrived={result['arrived_count']}/"
                        f"{result['agent_count']}"
                    )

                rows.append({
                    "trial": trial,
                    "seed": seed,
                    "alpha": alpha,
                    "social_cost": result["total_cost"],
                    "average_agent_cost": result["average_cost"],
                    "timesteps": result["timesteps"],
                    "agent_count": result["agent_count"],
                })

                print(
                    f"Trial {trial + 1}/{trials} | "
                    f"alpha={alpha:.2f} | "
                    f"cost={result['total_cost']:.4f}"
                )

    # Save every individual simulation.
    raw_path = output_dir / "raw_results.csv"

    with raw_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(rows[0].keys()),
        )
        writer.writeheader()
        writer.writerows(rows)

    # Aggregate results by alpha.
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
        })

    summary_path = output_dir / "summary.csv"

    with summary_path.open(
        "w", newline="", encoding="utf-8"
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(summary[0].keys()),
        )
        writer.writeheader()
        writer.writerows(summary)

    return summary


def plot_results(summary, output_dir):
    import matplotlib.pyplot as plt

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


def main():
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

    summary = run_alpha_sweep(
        scenario_dir=args.scenario,
        output_dir=args.output,
        trials=args.trials,
        alpha_step=args.alpha_step,
        base_seed=args.seed,
    )

    plot_results(summary, args.output)

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
