from collections import Counter
import random

import networkx as nx

from src.components.agent import Agent, InformationModel
from src.components.network import Network
from src.components.routing_strategies import SelfishRouting


class Simulation:
    def __init__(self, network, agents, record_history=True, seed=None):
        self.network = network
        self.agents = agents
        self.routing = SelfishRouting()
        self.timestep = 0
        self.record_history = record_history
        self.history = []
        self.rng = random.Random(seed)
        self._validate()

    def _validate(self):
        ids = [agent.agent_id for agent in self.agents]
        if len(ids) != len(set(ids)):
            raise ValueError("Agent IDs must be unique")
        for agent in self.agents:
            if agent.origin not in self.network.graph or agent.destination not in self.network.graph:
                raise ValueError(f"Agent {agent.agent_id}: unknown origin/destination")
            if not nx.has_path(self.network.graph, agent.origin, agent.destination):
                raise ValueError(f"Agent {agent.agent_id}: destination is unreachable")

    def all_agents_arrived(self):
        return all(agent.arrived for agent in self.agents)

    def step(self):
        if self.all_agents_arrived():
            return None

        previous_flows = {
            (u, v): data["edge"].flow
            for u, v, data in self.network.graph.edges(data=True)
        }

        # Phase 1: all agents choose using the same free-flow snapshot.
        # No provisional choices are committed or exposed during this phase.
        free_flow_costs = {
            (u, v): data["edge"].cost(flow=0)
            for u, v, data in self.network.graph.edges(data=True)
        }
        intentions = []
        for agent in self.agents:
            if agent.arrived:
                continue
            next_node = self.routing.choose_next_node(
                agent, self.network.graph, free_flow_costs
            )
            if next_node is not None:
                intentions.append({
                    "agent": agent,
                    "source": agent.current_node,
                    "target": next_node,
                })

        # Phase 2: sample the *frozen* provisional intentions. Every agent
        # revises once; revisions are not revealed until all have decided.
        decisions = []
        for intention in intentions:
            agent = intention["agent"]
            perceived_costs = InformationModel(
                agent.alpha, rng=self.rng
            ).get_perceived_costs(self.network, intentions, agent=agent)

            # Include the agent's own possible entry on the first edge.
            # The common free-flow remainder is unchanged, so no other
            # edge receives a fictitious contribution from this agent.
            candidate_costs = dict(perceived_costs)
            for _, target in self.network.graph.out_edges(agent.current_node):
                edge = self.network.get_edge(agent.current_node, target)
                estimated_others = (
                    (perceived_costs[(agent.current_node, target)] - edge.a) / edge.b
                    if edge.b > 0 else 0
                )
                candidate_costs[(agent.current_node, target)] = edge.cost(
                    flow=estimated_others + 1
                )

            next_node = self.routing.choose_next_node(
                agent, self.network.graph, candidate_costs
            )
            if next_node is not None:
                decisions.append({
                    "agent": agent,
                    "source": agent.current_node,
                    "target": next_node,
                    "initial_target": intention["target"],
                    "perceived_cost": candidate_costs[(agent.current_node, next_node)],
                })

        # Phase 3: commit all final choices simultaneously.
        new_flows = Counter((d["source"], d["target"]) for d in decisions)
        for u, v, data in self.network.graph.edges(data=True):
            data["edge"].flow = new_flows[(u, v)]

        decision_log = []
        for decision in decisions:
            agent = decision["agent"]
            source, target = decision["source"], decision["target"]
            actual_cost = self.network.get_edge(source, target).cost()
            agent.move(target, actual_cost)
            decision_log.append({
                "agent_id": agent.agent_id,
                "source": source,
                "target": target,
                "initial_target": decision["initial_target"],
                "reassessed": target != decision["initial_target"],
                "perceived_cost": decision["perceived_cost"],
                "actual_cost": actual_cost,
            })

        snapshot = {
            "timestep": self.timestep,
            "previous_flows": previous_flows,
            "initial_flows": dict(Counter(
                (d["source"], d["target"]) for d in intentions
            )),
            "decisions": decision_log,
            "new_flows": dict(new_flows),
            "positions": {agent.agent_id: agent.current_node for agent in self.agents},
            "total_cost": sum(agent.total_cost for agent in self.agents),
        }
        if self.record_history:
            self.history.append(snapshot)
        self.timestep += 1
        return snapshot

    def run(self, max_steps=100):
        """Yield up to max_steps additional steps (legacy API)."""
        for _ in range(max_steps):
            if self.all_agents_arrived():
                break
            yield self.step()

    def run_until_complete(self, max_steps=10000):
        if max_steps < 0:
            raise ValueError("max_steps must be nonnegative")
        for _ in self.run(max_steps=max_steps):
            pass
        return self.results()

    def results(self):
        completed = self.all_agents_arrived()
        total_cost = sum(agent.total_cost for agent in self.agents)
        return {
            "completed": completed,
            "status": "completed" if completed else "max_steps_reached",
            "timesteps": self.timestep,
            "agent_count": len(self.agents),
            "arrived_count": sum(agent.arrived for agent in self.agents),
            "total_cost": total_cost,
            "average_cost": total_cost / len(self.agents) if self.agents else 0.0,
            "agents": [
                {
                    "id": agent.agent_id,
                    "origin": agent.origin,
                    "destination": agent.destination,
                    "alpha": agent.alpha,
                    "arrived": agent.arrived,
                    "route": agent.route_history,
                    "cost": agent.total_cost,
                }
                for agent in self.agents
            ],
        }


def display_step(snapshot):
    print(f"\n--- Timestep {snapshot['timestep']} ---")
    print("Previous congestion:", snapshot["previous_flows"])
    print("Initial intentions:", snapshot["initial_flows"])
    for d in snapshot["decisions"]:
        print(
            f"Agent {d['agent_id']}: {d['source']} -> {d['target']} "
            f"(initially {d['initial_target']}) | "
            f"Perceived: {d['perceived_cost']:.2f} | Actual: {d['actual_cost']:.2f}"
        )
    print("Updated congestion:", snapshot["new_flows"])
    print("Agent positions:", snapshot["positions"])
    print(f"Accumulated cost: {snapshot['total_cost']:.2f}")


if __name__ == "__main__":
    network = Network()
    for u, v, a, b in [(1, 2, 2, 1), (2, 4, 2, 1),
                       (1, 3, 3, 0.2), (3, 4, 3, 0.2)]:
        network.add_edge(u, v, a=a, b=b)
    agents = [Agent(agent_id=i, origin=1, destination=4) for i in range(5)]
    sim = Simulation(network, agents)
    for snapshot in sim.run():
        display_step(snapshot)
    print(sim.results())
