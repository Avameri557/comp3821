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

Controllers and short-sellers:
  - Each controller runs fake agents (N - 1 by default). Their announcements
    look exactly like real agents' but they never travel or add congestion.
    Shield fakes copy the controller's route, so its road looks full and real
    agents avoid it. If there are rival controllers, a share of the fakes
    (herd_share) are herding fakes instead: each takes a real agent's origin
    and destination and announces the cheapest empty-road path that avoids
    every rival's congestible edges, so the roads around the rivals look full
    and traffic is pushed onto them. A controller ignores its own fakes.
  - A short-seller sees announcements like anyone else (each with probability
    alpha) and recognises every fake one it sees. It publishes them at once,
    ignores them when it plans, and plans selfishly. Every other agent, each
    time it reviews its plan, reads the published list with probability
    alpha and then ignores the fakes on it.
"""

from collections import Counter
from dataclasses import dataclass
import random

import networkx as nx

from src.components.agent import Agent, InformationModel
from src.components.routing_strategies import SelfishRouting


@dataclass
class FakeAgent:
    """An announcement with no real agent behind it, run by a controller."""
    fake_id: tuple
    owner: object        # the controller (an Agent)
    traveller: object    # herding fakes: an Agent with the fake's origin and destination; shield fakes: None


class Simulation:
    def __init__(self, network, agents, seed=None, revision_percentage=100, forward_only=True,
                 cap_estimates=False, fake_agents=None, herd_share=0.5):
        if isinstance(revision_percentage, bool) or not isinstance(revision_percentage, (int, float)) \
                or not 0 <= revision_percentage <= 100:
            raise ValueError("revision_percentage must be a number between 0 and 100")
        if not isinstance(forward_only, bool):
            raise ValueError("forward_only must be true or false")
        if not isinstance(cap_estimates, bool):
            raise ValueError("cap_estimates must be true or false")
        if fake_agents is not None and (isinstance(fake_agents, bool) or not isinstance(fake_agents, int)
                                        or fake_agents < 0):
            raise ValueError("fake_agents must be a nonnegative integer")
        if isinstance(herd_share, bool) or not isinstance(herd_share, (int, float)) or not 0 <= herd_share <= 1:
            raise ValueError("herd_share must be a number between 0 and 1")
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
        self.fake_agents = len(agents) - 1 if fake_agents is None else fake_agents
        self.herd_share = herd_share
        self.fakes = []
        # Ids of the fake agents short-sellers have published.
        self.exposed = set()
        self._fakes_set_up = False
        self._setup_seed = None if seed is None else seed * 7919 + 5

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

    def set_up_fakes(self):
        """Give every controller its fake agents (done at the first step, so
        roles can be assigned after the simulation is created)."""
        self._fakes_set_up = True
        controllers = [agent for agent in self.agents if agent.role == "controller"]
        # A separate random stream, so fakes do not change the simulation's draws.
        rng = random.Random(self._setup_seed)
        herding = round(self.fake_agents * self.herd_share) if len(controllers) > 1 else 0
        for controller in controllers:
            for i in range(self.fake_agents):
                traveller = None
                if i < herding:
                    pattern = rng.choice(self.agents)
                    traveller = Agent(agent_id=-1, origin=pattern.origin, destination=pattern.destination)
                self.fakes.append(FakeAgent(("fake", controller.agent_id, i), controller, traveller))

    def herding_route(self, fake, routes):
        """Cheapest empty-road path for a herding fake that avoids every congestible
        edge on a rival controller's route (the controller's own route if there is none)."""
        rival_edges = {edge for agent in self.agents
                       if agent.role == "controller" and agent is not fake.owner
                       for edge in zip(routes[agent.agent_id], routes[agent.agent_id][1:])
                       if self.network.get_edge(*edge).b > 0}
        costs = {(u, v): None if (u, v) in rival_edges else data["edge"].cost(flow=0)
                 for u, v, data in self.network.graph.edges(data=True)}
        try:
            return self.routing.choose_path(fake.traveller, self.network.graph, costs,
                                            depth=self.depth_for(fake.traveller))
        except nx.NetworkXNoPath:
            return list(routes[fake.owner.agent_id])

    def all_agents_arrived(self):
        return all(agent.arrived for agent in self.agents)

    def step(self):
        graph = self.network.graph
        if not self._fakes_set_up:
            self.set_up_fakes()

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
            intentions.append({"id": agent.agent_id, "agent": agent, "route": list(route)})
        travelling = [item for item in intentions if not item["agent"].arrived]

        #    Controllers' fake agents announce too: shield fakes copy their
        #    controller's route, herding fakes avoid the rivals' roads.
        routes = {item["id"]: item["route"] for item in intentions}
        shields, herding = {}, {}
        for fake in self.fakes:
            if fake.traveller:
                key = (fake.owner.agent_id, fake.traveller.origin, fake.traveller.destination)
                if key not in herding:
                    herding[key] = self.herding_route(fake, routes)
                route = list(herding[key])
            else:
                route = list(routes[fake.owner.agent_id])
            intentions.append({"id": fake.fake_id, "agent": None, "route": route})
            if not fake.traveller:
                shields.setdefault(fake.owner.agent_id, []).append(intentions[-1])
        own_fakes = {}
        for fake in self.fakes:
            own_fakes.setdefault(fake.owner.agent_id, set()).add(fake.fake_id)

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
            # Fakes the agent knows about: a controller's own, and the published ones
            # (a short-seller always knows them; anyone else reads the list with probability alpha).
            ignore = set(own_fakes.get(agent.agent_id, ()))
            if agent.role == "short_seller" or (self.exposed and self.rng.random() < agent.alpha):
                ignore |= self.exposed
            seen = model.observe_routes(intentions, agent=agent, ignore=ignore)
            if agent.role == "short_seller":
                # It recognises every fake it sees, publishes them and ignores them.
                self.exposed |= {item["id"] for item in seen if item["agent"] is None}
                seen = [item for item in seen if item["agent"] is not None]
            observed = model.count_edges(seen)
            perceived = {}
            for u, v, data in graph.edges(data=True):
                edge = data["edge"]
                others = model.estimate_load(observed, (u, v), cap=self.estimate_cap)
                # Own cost: the others expected on the edge over the whole run, plus this agent.
                perceived[(u, v)] = edge.cost(flow=others + 1)
                if agent.role == "social":
                    # Plus the delay this agent would add for each of those others:
                    # a + b(f + 1) + b f = a + b(2f + 1), the marginal social cost.
                    perceived[(u, v)] += edge.b * others
            plan = self.routing.choose_path(agent, graph, perceived, depth=self.depth_for(agent))
            intention["route"] = list(agent.route_history) + plan[1:]
            # A controller's shield fakes follow its new route.
            for shield in shields.get(agent.agent_id, ()):
                shield["route"] = list(intention["route"])

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
                    "role": agent.role,
                    "arrived": agent.arrived,
                    "route": agent.route_history,
                    "cost": agent.total_cost,
                }
                for agent in self.agents
            ],
        }
