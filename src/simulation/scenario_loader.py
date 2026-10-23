import json
import random
from pathlib import Path

from src.components.agent import Agent
from src.components.network import Network
from src.simulation.simulator import Simulation

import networkx as nx

<<<<<<< HEAD
def generate_agents(spec, network, rng, id_start=0, heat=0, release_time=0):
    # Generates agents from a total count, candidate src/dest nodes and alpha
=======
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
>>>>>>> main
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
        Agent(agent_id=id_start + i, origin=origin, destination=destination, alpha=alpha,
              heat=heat, release_time=release_time)
        for i in range(count)
        for origin, destination in [rng.choice(valid_pairs)]
    ]

<<<<<<< HEAD

def read_cascade(config):
    """(heats, heat_interval, enabled) from config["cascade"], if present.

    "cascade": {"heats": 20, "heat_interval": 1}
    releases the agents of agents.json once per heat, a new heat every
    heat_interval timesteps, and turns on edge memory (agents may see the
    cost each edge had the last time it was used).
    """
    cascade = config.get("cascade")
    if cascade is None:
        return 1, 0, False
    if not isinstance(cascade, dict):
        raise ValueError("cascade must be an object, e.g. {\"heats\": 20, \"heat_interval\": 1}")
    heats = cascade.get("heats", 1)
    interval = cascade.get("heat_interval", 1)
    for name, value, minimum in (("heats", heats, 1), ("heat_interval", interval, 0)):
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            raise ValueError(f"cascade.{name} must be an integer >= {minimum}")
    return heats, interval, True

def load_scenario(directory, seed=None):
    """Load a scenario folder. `seed`, if given, overrides config.json's seed
    (it controls both agent generation and the simulation's random draws)."""
=======
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
>>>>>>> main
    directory = Path(directory)
    def read(name):
        with (directory / name).open(encoding="utf-8") as f:
            return json.load(f)

    network_data = read("network.json")
    agent_data = read("agents.json")
    config = read("config.json") if (directory / "config.json").exists() else {}
    config.update(overrides or {})

    # Each simulated agent can stand for several vehicles. This only affects
    # BPR edges, whose capacities are in vehicles: an agent count f is costed
    # as f * vehicles_per_agent vehicles (equivalently capacity / vehicles_per_agent).
    vehicles_per_agent = config.get("vehicles_per_agent", 1)
    if isinstance(vehicles_per_agent, bool) or not isinstance(vehicles_per_agent, (int, float)) or vehicles_per_agent <= 0:
        raise ValueError("vehicles_per_agent must be a positive number")

    network = Network()
    for node in network_data.get("nodes", []):
        network.graph.add_node(node)
    for edge in network_data["edges"]:
        cost = edge.get("cost", edge)
        cost_type = cost.get("type", "linear")
        if cost_type == "linear":
            network.add_edge(edge["from"], edge["to"], a=cost["a"], b=cost["b"])
        elif cost_type == "bpr":
            # BPR: free_flow_time * (1 + alpha * (flow / capacity) ** beta)
            network.add_bpr_edge(
                edge["from"], edge["to"],
                free_flow_time=cost["free_flow_time"],
                capacity=cost["capacity"] / vehicles_per_agent,
                alpha=cost.get("alpha", 0.15),
                beta=cost.get("beta", 4),
            )
        else:
            raise ValueError(f"Unsupported edge cost type {cost_type!r} (use 'linear' or 'bpr')")

    max_steps = config.get("max_timesteps", 10000)
    if not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps < 0:
        raise ValueError("max_timesteps must be a nonnegative integer")
    
    if seed is None:
        seed = config.get("seed")
    if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
        raise ValueError("seed must be an integer")

    if ("generate" in agent_data) == ("agents" in agent_data):
        raise ValueError("agents.json must contain exactly one of 'agents' or 'generate'")

    heats, heat_interval, cascade = read_cascade(config)

    # agents.json describes one heat; in cascade mode it is repeated per heat.
    agents = []
    if "generate" in agent_data:
        rng = random.Random(seed)
        for heat in range(heats):
            agents += generate_agents(
                agent_data["generate"], network, rng,
                id_start=len(agents), heat=heat, release_time=heat * heat_interval,
            )
    else:
        items = agent_data["agents"]
        id_step = max((item["id"] for item in items), default=-1) + 1
        for heat in range(heats):
            agents += [
                Agent(
                    agent_id=item["id"] + heat * id_step,
                    origin=item["origin"],
                    destination=item["destination"],
                    alpha=item.get("alpha", 1.0),
                    heat=heat,
                    release_time=heat * heat_interval,
                )
                for item in items
            ]

    revision_percentage = config.get("revision_percentage", 100)
    if isinstance(revision_percentage, bool) or not isinstance(revision_percentage, (int, float)) or not 0 <= revision_percentage <= 100:
        raise ValueError("revision_percentage must be a number between 0 and 100")
    
    forward_only = config.get("forward_only", True)
    if not isinstance(forward_only, bool):
        raise ValueError("forward_only must be true or false")

    simulation = Simulation(
        network, agents,
        record_history=config.get("record_history", False),
        seed=seed,
        revision_percentage=revision_percentage,
        forward_only=forward_only,
        edge_memory=cascade,
    )
    return simulation, config