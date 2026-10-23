from collections import Counter
import random

import networkx as nx

from src.components.agent import Agent, InformationModel
from src.components.network import Network
from src.components.routing_strategies import SelfishRouting


class Simulation:
    def __init__(self, network, agents, record_history=True, seed=None, revision_percentage=100,
                 forward_only=True, edge_memory=False):
        self.network = network
        self.agents = agents
        self.routing = SelfishRouting()
        self.timestep = 0
        self.record_history = record_history
        self.history = []
        if isinstance(revision_percentage, bool) or not isinstance(revision_percentage, (int, float)) or not 0 <= revision_percentage <= 100:
            raise ValueError("revision_percentage must be a number between 0 and 100")
        self.revision_percentage = revision_percentage
        if not isinstance(forward_only, bool):
            raise ValueError("forward_only must be true or false")
        # Agents only move forwards: never to a node closer (in hops) to their
        # own origin than where they are, and never back to a visited node.
        self.forward_only = forward_only
        self._depth_from = {}
        # Edge memory (cascade mode): every edge remembers the cost it had the
        # last time any agent crossed it. Unused edges show their base cost.
        if not isinstance(edge_memory, bool):
            raise ValueError("edge_memory must be true or false")
        self.edge_memory = edge_memory
        self.last_cost = {
            (u, v): data["edge"].cost(flow=0)
            for u, v, data in self.network.graph.edges(data=True)
        }
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

    def depth_for(self, agent):
        """Hop distance of every node from the agent's origin (None if unrestricted)."""
        if not self.forward_only:
            return None
        if agent.origin not in self._depth_from:
            self._depth_from[agent.origin] = nx.single_source_shortest_path_length(
                self.network.graph, agent.origin
            )
        return self._depth_from[agent.origin]

    def all_agents_arrived(self):
        return all(agent.arrived for agent in self.agents)

    def is_active(self, agent):
        """Released into the graph and still travelling."""
        return not agent.arrived and agent.release_time <= self.timestep

    def step(self):
        if self.all_agents_arrived():
            return None
        previous_flows = {
            (u, v): data["edge"].flow
            for u, v, data in self.network.graph.edges(data=True)
        }

        # Agents pick a path based on previous flow snapshot
        free_flow_costs = {
            (u, v): data["edge"].cost(flow=0)
            for u, v, data in self.network.graph.edges(data=True)
        }
        intentions = []
        for agent in self.agents:
            if not self.is_active(agent):
                continue
            next_node = self.routing.choose_next_node(
                agent, self.network.graph, free_flow_costs, depth=self.depth_for(agent)
            )
            if next_node is not None:
                intentions.append({
                    "agent": agent,
                    "source": agent.current_node,
                    "target": next_node,
                })

        # Select an exact percentage (rounded to nearest agent) for reassessment.
        review_count = int(len(intentions) * self.revision_percentage / 100 + 0.5)
        reviewers = {id(item) for item in self.rng.sample(intentions, review_count)}

        # Check other agent intentions exactly once. Revisions are not revealed until after
        decisions = []
        for intention in intentions:
            agent = intention["agent"]
            if id(intention) not in reviewers:
                source, target = intention["source"], intention["target"]
                decisions.append({
                    "agent": agent, "source": source, "target": target,
                    "initial_target": target,
                    "perceived_cost": free_flow_costs[(source, target)],
                    "review_eligible": False,
                })
                continue

            model = InformationModel(agent.alpha, rng=self.rng)
            observed = model.observe_intentions(intentions, agent=agent)
            estimated_others = model.estimate_flows(self.network, observed=observed)

            if not self.edge_memory:
                candidate_costs = {
                    (u, v): data["edge"].cost(flow=estimated_others[(u, v)])
                    for u, v, data in self.network.graph.edges(data=True)
                }

                # Include the agent's own decision when comparing the initial edge.
                # Original scan does not include itself
                for _, target in self.network.graph.out_edges(agent.current_node):
                    edge = self.network.get_edge(agent.current_node, target)
                    candidate_costs[(agent.current_node, target)] = edge.cost(
                        flow=estimated_others[(agent.current_node, target)] + 1
                    )
            else:
                # Cascade mode. Each edge, in order of preference:
                #   1. saw at least one announced move on it -> estimate from announcements
                #   2. sees the edge's previous cost (prob. alpha) -> that cost
                #   3. otherwise -> base cost
                # The agent's own +1 is added on edges leaving its current node
                # in cases 1 and 3 (a previous cost is used as it was paid).
                seen_previous = model.observe_previous_costs(self.last_cost)
                candidate_costs = {}
                for u, v, data in self.network.graph.edges(data=True):
                    own = 1 if u == agent.current_node else 0
                    if observed.get((u, v), 0) > 0:
                        candidate_costs[(u, v)] = data["edge"].cost(flow=estimated_others[(u, v)] + own)
                    elif (u, v) in seen_previous:
                        candidate_costs[(u, v)] = seen_previous[(u, v)]
                    else:
                        candidate_costs[(u, v)] = data["edge"].cost(flow=own)

            next_node = self.routing.choose_next_node(
                agent, self.network.graph, candidate_costs, depth=self.depth_for(agent)
            )
            if next_node is not None:
                decisions.append({
                    "agent": agent,
                    "source": agent.current_node,
                    "target": next_node,
                    "initial_target": intention["target"],
                    "review_eligible": True,
                    "perceived_cost": candidate_costs[(agent.current_node, next_node)],
                })

        # Lock in final decision
        new_flows = Counter((d["source"], d["target"]) for d in decisions)
        for u, v, data in self.network.graph.edges(data=True):
            data["edge"].flow = new_flows[(u, v)]
            if new_flows[(u, v)] > 0:
                self.last_cost[(u, v)] = data["edge"].cost()

        decision_log = []
        for decision in decisions:
            agent = decision["agent"]
            source, target = decision["source"], decision["target"]
            actual_cost = self.network.get_edge(source, target).cost()
            agent.move(target, actual_cost)
            decision_log.append({
                "agent_id": agent.agent_id,
                "source": source,
                "initial_target": decision["initial_target"],
                "reassessed": target != decision["initial_target"],
                "review_eligible": decision["review_eligible"],
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
            "active_count": len(intentions),
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
            "heats": self.heat_summary(),
            "agents": [
                {
                    "id": agent.agent_id,
                    "heat": agent.heat,
                    "release_time": agent.release_time,
                    "origin": agent.origin,
                    "destination": agent.destination,
                    "alpha": agent.alpha,
                    "arrived": agent.arrived,
                    "route": agent.route_history,
                    "steps": len(agent.route_history) - 1,
                    "cost": agent.total_cost,
                }
                for agent in self.agents
            ],
        }

    def heat_summary(self):
        """Average cost per heat, overall and per alpha value."""
        heats = {}
        for agent in self.agents:
            heats.setdefault(agent.heat, []).append(agent)
        summary = []
        for heat in sorted(heats):
            members = heats[heat]
            by_alpha = {}
            for agent in members:
                by_alpha.setdefault(agent.alpha, []).append(agent.total_cost)
            summary.append({
                "heat": heat,
                "release_time": min(a.release_time for a in members),
                "agents": len(members),
                "arrived": sum(a.arrived for a in members),
                "average_cost": sum(a.total_cost for a in members) / len(members),
                "average_cost_by_alpha": {
                    str(alpha): sum(costs) / len(costs) for alpha, costs in sorted(by_alpha.items())
                },
            })
        return summary


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