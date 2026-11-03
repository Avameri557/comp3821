from dataclasses import dataclass, field
import random


@dataclass
class Agent:
    agent_id: int
    origin: int
    destination: int
    alpha: float = 1.0

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

    def move(self, next_node: int):
        self.current_node = next_node
        self.route_history.append(next_node)
        if self.current_node == self.destination:
            self.arrived = True


class InformationModel:
    """What one agent sees of the other agents' announced routes."""

    def __init__(self, alpha=1.0, rng=None):
        if not 0 <= alpha <= 1:
            raise ValueError("alpha must be between 0 and 1")
        self.alpha = alpha
        self.rng = rng if rng is not None else random.Random()

    def observe_routes(self, intentions, agent=None):
        """Count K[edge]: other agents seen with `edge` on their route.

        Each other agent's whole route (the edges it has crossed plus its
        current plan) is seen independently with probability alpha.
        """
        observed = {}
        for intention in intentions:
            if agent is not None and intention["agent"].agent_id == agent.agent_id:
                continue
            if self.rng.random() < self.alpha:
                route = intention["route"]
                for edge in zip(route, route[1:]):
                    observed[edge] = observed.get(edge, 0) + 1
        return observed

    def estimate_load(self, observed, edge):
        """Estimated number of *other* agents using `edge`: K / alpha (unbiased)."""
        return observed.get(edge, 0) / self.alpha if self.alpha else 0.0
