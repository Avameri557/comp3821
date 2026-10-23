"""
Shared helpers for the visualisation tools: information mixes ("populations"),
building a simulation with a given mix, and per-agent run summaries.

A population spec is a comma-separated list of alpha[:share] groups:
    "1.0"                 every agent has alpha = 1
    "1.0:0.2,0.0"         20% of agents have alpha = 1, the rest alpha = 0
    "1.0:0.1,0.5:0.3,0"   10% alpha 1, 30% alpha 0.5, the rest alpha 0
Groups without a share split whatever is left equally. Agents are assigned
to groups at random (independently of origin/destination), seeded.
"""

import random
from pathlib import Path

from src.simulation.scenario_loader import load_scenario


def parse_population(spec):
    """Parse a population spec into [(alpha, share), ...]. None -> None."""
    if spec is None:
        return None
    groups = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            alpha, share = part.split(":", 1)
            groups.append((float(alpha), float(share)))
        else:
            groups.append((float(part), None))
    if not groups:
        raise ValueError(f"Empty population spec {spec!r}")
    for alpha, share in groups:
        if not 0 <= alpha <= 1:
            raise ValueError(f"alpha {alpha} must be between 0 and 1")
        if share is not None and not 0 <= share <= 1:
            raise ValueError(f"share {share} must be between 0 and 1")
    given = sum(share for _, share in groups if share is not None)
    missing = [i for i, (_, share) in enumerate(groups) if share is None]
    if given > 1 + 1e-9:
        raise ValueError(f"Shares in {spec!r} add up to more than 1")
    if missing:
        fill = (1 - given) / len(missing)
        groups = [(alpha, fill if share is None else share) for alpha, share in groups]
    elif abs(given - 1) > 1e-6:
        raise ValueError(f"Shares in {spec!r} must add up to 1")
    return groups


def describe_population(groups, agents=None):
    """Short human-readable label, e.g. 'α=1: 20%, α=0: 80%'."""
    if groups is None:
        if agents:
            alphas = sorted({a.alpha for a in agents}, reverse=True)
            if len(alphas) == 1:
                return f"all α={alphas[0]:g}"
            return "scenario α: " + ", ".join(f"{a:g}" for a in alphas)
        return "scenario α"
    if len(groups) == 1:
        return f"all α={groups[0][0]:g}"
    return ", ".join(f"α={a:g}: {s:.0%}" for a, s in groups)


def group_counts(n, groups):
    """Split n agents into groups by share (largest-remainder rounding)."""
    raw = [share * n for _, share in groups]
    counts = [int(x) for x in raw]
    leftover = n - sum(counts)
    order = sorted(range(len(groups)), key=lambda i: raw[i] - counts[i], reverse=True)
    for i in order[:leftover]:
        counts[i] += 1
    return counts


def assign_alphas(agents, groups, rng):
    """Give each agent an alpha according to the group shares, at random."""
    order = list(range(len(agents)))
    rng.shuffle(order)
    start = 0
    for (alpha, _), count in zip(groups, group_counts(len(agents), groups)):
        for j in order[start:start + count]:
            agents[j].alpha = alpha
        start += count


def make_simulation(scenario, groups=None, seed=None, record_history=True):
    """Load a scenario, optionally override its seed and information mix."""
    simulation, config = load_scenario(Path(scenario), seed=seed)
    simulation.record_history = record_history
    if groups is not None:
        # Separate stream so the mix does not disturb the simulation's own draws.
        mix_seed = config.get("seed", 0) if seed is None else seed
        assign_alphas(simulation.agents, groups, random.Random(mix_seed * 7919 + 17))
    return simulation, config


def run_summary(scenario, groups=None, seed=None, max_steps=None):
    """Run one simulation without history and return per-agent outcomes.

    Picklable inputs/outputs so it can run in a process pool.
    """
    simulation, config = make_simulation(scenario, groups, seed, record_history=False)
    if max_steps is None:
        max_steps = config.get("max_timesteps", 10000)
    result = simulation.run_until_complete(max_steps)
    return {
        "seed": seed,
        "completed": result["completed"],
        "timesteps": result["timesteps"],
        "agents": [
            {
                "alpha": agent["alpha"],
                "heat": agent["heat"],
                "release_time": agent["release_time"],
                "cost": agent["cost"],
                "arrived": agent["arrived"],
                # Steps (edges) taken until arrival; None if it never arrived.
                "steps": len(agent["route"]) - 1 if agent["arrived"] else None,
            }
            for agent in result["agents"]
        ],
    }
