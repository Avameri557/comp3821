"""
Step-based routing simulation with partial information.

Congestion counts the whole run: an edge costs a + b * x, where x is the
number of agents whose route uses it at any point. Each agent pays the cost
of every edge on its final route, worked out once the run ends (the same
model as the Wardrop and optimum benchmarks).

Every step:
  1. Each agent announces its current route: the whole route it chose last
     step, including the edges it has already crossed. Before an agent's
     first decision, that is its cheapest path on empty-road costs. Agents
     that have arrived announce the route they took.
  2. Agents still travelling decide one at a time, in a new random order every
     step. A share of them (revision_percentage) reviews its plan: a reviewing
     agent sees each other agent's whole route with probability alpha (the
     revised route for agents that have already decided this step, the
     announcement for the rest). It estimates every edge's load as (routes
     seen using that edge) / alpha, adds itself, and re-plans its cheapest
     remaining path. Its new route replaces its announcement for the agents
     after it.
  3. All agents still travelling move one edge.
Agents re-plan every step; only the first edge of a plan is ever committed.
"""

from collections import Counter
import random

import networkx as nx

from src.components.agent import InformationModel
from src.components.routing_strategies import SelfishRouting


class Simulation:
    def __init__(self, network, agents, seed=None, revision_percentage=100, forward_only=True,
                 cap_estimates=False):
        if isinstance(revision_percentage, bool) or not isinstance(revision_percentage, (int, float)) \
                or not 0 <= revision_percentage <= 100:
            raise ValueError("revision_percentage must be a number between 0 and 100")
        if not isinstance(forward_only, bool):
            raise ValueError("forward_only must be true or false")
        if not isinstance(cap_estimates, bool):
            raise ValueError("cap_estimates must be true or false")
        self.network = network
        self.agents = agents
        self.routing = SelfishRouting()
        self.timestep = 0
        self.revision_percentage = revision_percentage
        # Agents only move forwards: never to a node closer (in hops) to their
        # own origin than where they are, and never back to a visited node.
        self.forward_only = forward_only
        # Agents know how many agents there are, so no estimated load on an edge
        # can exceed the number of other agents.
        self.estimate_cap = len(agents) - 1 if cap_estimates else None
        self._depth_from = {}
        # Each agent's most recently chosen route (from its origin), announced every step.
        self.current_routes = {}
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

        # 1. Every agent announces its current route: the route it chose last
        #    step (which starts with the edges it has crossed). Before an agent's
        #    first decision, that is its cheapest path on empty-road costs.
        free_flow_costs = {(u, v): data["edge"].cost(flow=0) for u, v, data in graph.edges(data=True)}
        intentions = []
        for agent in self.agents:
            route = self.current_routes.get(agent.agent_id)
            if route is None:
                route = (list(agent.route_history) if agent.arrived else
                         self.routing.choose_path(agent, graph, free_flow_costs, depth=self.depth_for(agent)))
            intentions.append({"agent": agent, "route": list(route)})
        travelling = [item for item in intentions if not item["agent"].arrived]

        # 2. An exact share of travelling agents (rounded to the nearest agent)
        #    reviews its plan. Agents decide one at a time, in a new random order
        #    every step; a reviewer's new route replaces its announcement, so
        #    agents later in the order see it instead of the original.
        review_count = int(len(travelling) * self.revision_percentage / 100 + 0.5)
        reviewers = {id(item) for item in self.rng.sample(travelling, review_count)}
        order = list(travelling)
        self.rng.shuffle(order)
        for intention in order:
            agent = intention["agent"]
            if id(intention) not in reviewers:
                continue
            model = InformationModel(agent.alpha, rng=self.rng)
            observed = model.observe_routes(intentions, agent=agent)
            perceived = {}
            for u, v, data in graph.edges(data=True):
                edge = data["edge"]
                others = model.estimate_load(observed, (u, v), cap=self.estimate_cap)
                # Own cost: the others expected on the edge over the whole run, plus this agent.
                perceived[(u, v)] = edge.cost(flow=others + 1)
                if agent.social:
                    # Plus the delay this agent would add for each of those others:
                    # a + b(f + 1) + b f = a + b(2f + 1), the marginal social cost.
                    perceived[(u, v)] += edge.b * others
            plan = self.routing.choose_path(agent, graph, perceived, depth=self.depth_for(agent))
            intention["route"] = list(agent.route_history) + plan[1:]

        # 3. Everyone still travelling moves one edge along its route; the route
        #    is kept as its announcement for the next step.
        for intention in travelling:
            agent = intention["agent"]
            agent.move(intention["route"][len(agent.route_history)])
            self.current_routes[agent.agent_id] = intention["route"]
        self.timestep += 1

    def settle_costs(self):
        """Load every edge with the agents whose route uses it, then charge each
        agent the cost of every edge on its route."""
        loads = Counter(edge for agent in self.agents
                        for edge in zip(agent.route_history, agent.route_history[1:]))
        for u, v, data in self.network.graph.edges(data=True):
            data["edge"].flow = loads[(u, v)]
        for agent in self.agents:
            agent.total_cost = sum(self.network.get_edge(u, v).cost()
                                   for u, v in zip(agent.route_history, agent.route_history[1:]))

    def run_until_complete(self, max_steps=10000):
        if max_steps < 0:
            raise ValueError("max_steps must be nonnegative")
        while self.timestep < max_steps and not self.all_agents_arrived():
            self.step()
        self.settle_costs()
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
