"""
Step-based routing simulation with partial information.

Every step:
  1. Each agent still travelling plans its cheapest path on empty-road costs
     and announces its next edge.
  2. A share of agents (revision_percentage) reviews that plan. A reviewing
     agent sees each other agent's announcement with probability alpha,
     estimates the load on every edge as (announcements seen) / alpha, adds
     itself on the edges leaving its current node, and re-plans.
  3. All agents move one edge at the same time. An edge costs a + b * f,
     where f is the number of agents crossing it in that step.
"""

from collections import Counter
import random

import networkx as nx

from src.components.agent import InformationModel
from src.components.routing_strategies import SelfishRouting


class Simulation:
    def __init__(self, network, agents, seed=None, revision_percentage=100, forward_only=True):
        if isinstance(revision_percentage, bool) or not isinstance(revision_percentage, (int, float)) \
                or not 0 <= revision_percentage <= 100:
            raise ValueError("revision_percentage must be a number between 0 and 100")
        if not isinstance(forward_only, bool):
            raise ValueError("forward_only must be true or false")
        self.network = network
        self.agents = agents
        self.routing = SelfishRouting()
        self.timestep = 0
        self.revision_percentage = revision_percentage
        # Agents only move forwards: never to a node closer (in hops) to their
        # own origin than where they are, and never back to a visited node.
        self.forward_only = forward_only
        self._depth_from = {}
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

    def step(self):
        graph = self.network.graph

        # 1. Plans on empty-road costs; announce the next edge.
        free_flow_costs = {(u, v): data["edge"].cost(flow=0) for u, v, data in graph.edges(data=True)}
        intentions = []
        for agent in self.agents:
            if agent.arrived:
                continue
            next_node = self.routing.choose_next_node(agent, graph, free_flow_costs, depth=self.depth_for(agent))
            if next_node is not None:
                intentions.append({"agent": agent, "source": agent.current_node, "target": next_node})

        # 2. An exact share of agents (rounded to the nearest agent) reviews its plan.
        #    Everyone sees the original announcements, not other agents' revisions.
        review_count = int(len(intentions) * self.revision_percentage / 100 + 0.5)
        reviewers = {id(item) for item in self.rng.sample(intentions, review_count)}
        moves = []
        for intention in intentions:
            agent = intention["agent"]
            if id(intention) not in reviewers:
                moves.append((agent, intention["source"], intention["target"]))
                continue
            model = InformationModel(agent.alpha, rng=self.rng)
            estimated_others = model.estimate_flows(self.network, model.observe_intentions(intentions, agent=agent))
            perceived = {
                (u, v): data["edge"].cost(flow=estimated_others[(u, v)] + (1 if u == agent.current_node else 0))
                for u, v, data in graph.edges(data=True)
            }
            next_node = self.routing.choose_next_node(agent, graph, perceived, depth=self.depth_for(agent))
            if next_node is not None:
                moves.append((agent, agent.current_node, next_node))

        # 3. Everyone moves at once; each edge is costed at its flow this step.
        flows = Counter((source, target) for _, source, target in moves)
        for u, v, data in graph.edges(data=True):
            data["edge"].flow = flows[(u, v)]
        for agent, source, target in moves:
            agent.move(target, self.network.get_edge(source, target).cost())
        self.timestep += 1

    def run_until_complete(self, max_steps=10000):
        if max_steps < 0:
            raise ValueError("max_steps must be nonnegative")
        while self.timestep < max_steps and not self.all_agents_arrived():
            self.step()
        return self.results()

    def results(self):
        completed = self.all_agents_arrived()
        total_cost = sum(agent.total_cost for agent in self.agents)
        return {
            "completed": completed,
            "timesteps": self.timestep,
            "agent_count": len(self.agents),
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
