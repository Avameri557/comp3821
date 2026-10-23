from dataclasses import dataclass, field
import random

@dataclass
class Agent:
    agent_id: int
    origin: int
    destination: int
    alpha: float = 1.0
    heat: int = 0            # which heat (release wave) the agent belongs to
    release_time: int = 0    # timestep at which the agent enters the graph

    current_node: int = field(init=False)
    route_history: list[int] = field(init=False)
    total_cost: float = field(default=0.0, init=False)
    arrived: bool = field(default=False, init=False)

    def __post_init__(self):
        if not 0 <= self.alpha <= 1:
            raise ValueError("alpha must be between 0 and 1")

        self.current_node = self.origin
        self.route_history = [self.origin]
        self.arrived = self.origin == self.destination

    def move(self, next_node: int, cost: float):
        self.current_node = next_node
        self.route_history.append(next_node)
        self.total_cost += cost

        if self.current_node == self.destination:
            self.arrived = True


class InformationModel:
    def __init__(self, alpha=1.0, rng=None):
        if not 0 <= alpha <= 1:
            raise ValueError("alpha must be between 0 and 1")
        self.alpha = alpha
        self.rng = rng if rng is not None else random.Random()

    def observe_intentions(self, intentions=None, agent=None):
        """Count K_e of *other* agents' announced edges that this agent sees.

        Each other agent's intention is seen independently with probability alpha.
        """
        intentions = intentions or []
        observed = {}
        for intention in intentions:
            if agent is not None and intention["agent"].agent_id == agent.agent_id:
                continue
            edge = (intention["source"], intention["target"])
            if self.rng.random() < self.alpha:
                observed[edge] = observed.get(edge, 0) + 1
        return observed

    def estimate_flows(self, network, intentions=None, agent=None, observed=None):
        """Estimated number of *other* agents intending each edge.

        The observed count is scaled by 1/alpha (unbiased estimate).
        """
        if observed is None:
            observed = self.observe_intentions(intentions, agent)
        return {
            (u, v): (observed.get((u, v), 0) / self.alpha if self.alpha else 0)
            for u, v in network.graph.edges()
        }

    def observe_previous_costs(self, last_cost):
        """Previous costs of the edges this agent sees: each edge independently
        with probability alpha. Returns {edge: last realised cost}."""
        return {
            edge: cost
            for edge, cost in last_cost.items()
            if self.rng.random() < self.alpha
        }

    def get_perceived_costs(self, network, intentions=None, agent=None):
        estimated = self.estimate_flows(network, intentions, agent)
        return {
            (u, v): data["edge"].cost(flow=estimated[(u, v)])
            for u, v, data in network.graph.edges(data=True)
        }