import json
import random
from pathlib import Path

from src.components.agent import Agent
from src.components.network import Network
from src.simulation.simulator import Simulation

import networkx as nx

def generate_agents(spec, network, rng):
    """
    Create agents from the "generate" block of agents.json.

    Args:
        spec: Dict with "count", "sources", "destinations" and
            "alpha". Each agent gets a random reachable
            (source, destination) pair with source != destination.
        network: Network the nodes must belong to.
        rng: random.Random used to pick pairs, so a fixed seed
            gives the same agents every time.

    Returns:
        List of Agent objects with ids 0..count-1.

    Raises:
        ValueError: If the spec is malformed or no valid pair exists.
    """
    if not isinstance(spec, dict):
        raise ValueError("agents.generate must be an object")

    count = spec.get("count")
    sources = spec.get("sources")
    destinations = spec.get("destinations")
    alpha = spec.get("alpha")

    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("agents.generate.count must be a nonnegative integer")
    if not isinstance(sources, list) or not sources:
        raise ValueError("agents.generate.sources must be a nonempty array")
    if not isinstance(destinations, list) or not destinations:
        raise ValueError("agents.generate.destinations must be a nonempty array")
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not 0 <= alpha <= 1:
        raise ValueError("agents.generate.alpha must be a number between 0 and 1")

    for label, nodes in (("sources", sources), ("destinations", destinations)):
        for node in nodes:
            if node not in network.graph:
                raise ValueError(f"agents.generate.{label} contains unknown node {node!r}")
        if len(set(sources if label == "sources" else destinations)) != len(nodes):
            raise ValueError(f"agents.generate.{label} must not contain duplicate nodes")

    valid_pairs = [
        (source, destination)
        for source in sources
        for destination in destinations
        if source != destination and nx.has_path(network.graph, source, destination)
    ]
    if count and not valid_pairs:
        raise ValueError("No reachable source/destination pairs with distinct nodes")

    return [
        Agent(agent_id=i, origin=origin, destination=destination, alpha=alpha)
        for i in range(count)
        for origin, destination in [rng.choice(valid_pairs)]
    ]

def load_scenario(directory, overrides=None):
    """
    Build a Simulation from a scenario directory.

    Args:
        directory: Folder containing network.json, agents.json
            and (optionally) config.json.
        overrides: Optional dict of config values applied on top
            of config.json, e.g. {"seed": 7}. Validated like
            values read from the file. Files are not modified.

    Returns:
        (simulation, config), where config is the merged
        configuration actually used.

    Raises:
        ValueError: If the network, agents or config are invalid.
    """
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
        cost = edge.get("cost", edge)
        if cost.get("type", "linear") != "linear":
            raise ValueError("Only linear edge costs are supported")
        network.add_edge(edge["from"], edge["to"], a=cost["a"], b=cost["b"])

    max_steps = config.get("max_timesteps", 10000)
    if not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps < 0:
        raise ValueError("max_timesteps must be a nonnegative integer")
    
    seed = config.get("seed")
    if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
        raise ValueError("seed must be an integer")

    if ("generate" in agent_data) == ("agents" in agent_data):
        raise ValueError("agents.json must contain exactly one of 'agents' or 'generate'")

    if "generate" in agent_data:
        agents = generate_agents(agent_data["generate"], network, random.Random(seed))
    else:
        agents = [
            Agent(
                agent_id=item["id"],
                origin=item["origin"],
                destination=item["destination"],
                alpha=item.get("alpha", 1.0),
            )
            for item in agent_data["agents"]
        ]

    revision_percentage = config.get("revision_percentage", 100)
    if isinstance(revision_percentage, bool) or not isinstance(revision_percentage, (int, float)) or not 0 <= revision_percentage <= 100:
        raise ValueError("revision_percentage must be a number between 0 and 100")
    
    simulation = Simulation(
        network, agents,
        record_history=config.get("record_history", False),
        seed=seed,
        revision_percentage=revision_percentage,
    )
    return simulation, config