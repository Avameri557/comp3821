"""
Load a scenario folder:

    network.json   nodes and edges, each with a linear cost {"a": ..., "b": ...}
    agents.json    {"generate": {"count", "sources", "destinations", "alpha"}}
                   or {"agents": [{"id", "origin", "destination", "alpha"}, ...]}
    config.json    max_timesteps, seed, revision_percentage, forward_only, cap_estimates
"""

import json
import random
from pathlib import Path

import networkx as nx

from src.components.agent import Agent
from src.components.network import Network
from src.simulation.simulator import Simulation


def generate_agents(spec, network, rng):
    """Agents with a random reachable (source, destination) pair each (source != destination)."""
    count, sources, destinations, alpha = (spec.get(k) for k in ("count", "sources", "destinations", "alpha"))
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("agents.generate.count must be a nonnegative integer")
    for label, nodes in (("sources", sources), ("destinations", destinations)):
        if not isinstance(nodes, list) or not nodes:
            raise ValueError(f"agents.generate.{label} must be a nonempty array")
        if len(set(nodes)) != len(nodes):
            raise ValueError(f"agents.generate.{label} must not contain duplicate nodes")
        for node in nodes:
            if node not in network.graph:
                raise ValueError(f"agents.generate.{label} contains unknown node {node!r}")
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not 0 <= alpha <= 1:
        raise ValueError("agents.generate.alpha must be a number between 0 and 1")

    pairs = [(s, d) for s in sources for d in destinations if s != d and nx.has_path(network.graph, s, d)]
    if count and not pairs:
        raise ValueError("No reachable source/destination pairs with distinct nodes")
    agents = []
    for i in range(count):
        origin, destination = rng.choice(pairs)
        agents.append(Agent(agent_id=i, origin=origin, destination=destination, alpha=alpha))
    return agents


def load_scenario(directory, overrides=None, seed=None):
    """Return (simulation, config). `seed`, if given, replaces config.json's seed
    (it controls both agent generation and the simulation's random draws)."""
    directory = Path(directory)

    def read(name):
        with (directory / name).open(encoding="utf-8") as f:
            return json.load(f)

    network_data = read("network.json")
    agent_data = read("agents.json")
    config = read("config.json") if (directory / "config.json").exists() else {}
    config.update(overrides or {})

    network = Network()
    for node in network_data.get("nodes", []):
        network.graph.add_node(node)
    for edge in network_data["edges"]:
        cost = edge["cost"]
        if cost.get("type", "linear") != "linear":
            raise ValueError("Only linear edge costs are supported")
        network.add_edge(edge["from"], edge["to"], a=cost["a"], b=cost["b"])

    max_steps = config.get("max_timesteps", 100)
    if not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps < 0:
        raise ValueError("max_timesteps must be a nonnegative integer")
    if seed is None:
        seed = config.get("seed")
    if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
        raise ValueError("seed must be an integer")

    if ("generate" in agent_data) == ("agents" in agent_data):
        raise ValueError("agents.json must contain exactly one of 'agents' or 'generate'")
    if "generate" in agent_data:
        agents = generate_agents(agent_data["generate"], network, random.Random(seed))
    else:
        agents = [
            Agent(agent_id=item["id"], origin=item["origin"], destination=item["destination"],
                  alpha=item.get("alpha", 1.0), social=item.get("social", False))
            for item in agent_data["agents"]
        ]

    simulation = Simulation(
        network, agents,
        seed=seed,
        revision_percentage=config.get("revision_percentage", 100),
        forward_only=config.get("forward_only", True),
        cap_estimates=config.get("cap_estimates", False),
    )
    return simulation, config
