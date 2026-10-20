import json
from pathlib import Path

from src.components.agent import Agent
from src.components.network import Network
from src.simulation.simulator import Simulation


def load_scenario(directory):
    directory = Path(directory)
    def read(name):
        with (directory / name).open(encoding="utf-8") as f:
            return json.load(f)

    network_data = read("network.json")
    agent_data = read("agents.json")
    config = read("config.json") if (directory / "config.json").exists() else {}

    network = Network()
    for node in network_data.get("nodes", []):
        network.graph.add_node(node)
    for edge in network_data["edges"]:
        cost = edge.get("cost", edge)
        if cost.get("type", "linear") != "linear":
            raise ValueError("Only linear edge costs are supported")
        network.add_edge(edge["from"], edge["to"], a=cost["a"], b=cost["b"])

    agents = [
        Agent(
            agent_id=item["id"],
            origin=item["origin"],
            destination=item["destination"],
            alpha=item.get("alpha", 1.0),
        )
        for item in agent_data["agents"]
    ]
    max_steps = config.get("max_timesteps", 10000)
    if not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps < 0:
        raise ValueError("max_timesteps must be a nonnegative integer")
    
    seed = config.get("seed")
    if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
        raise ValueError("seed must be an integer")
    simulation = Simulation(
        network, agents,
        record_history=config.get("record_history", False),
        seed=seed,
    )
    return simulation, config