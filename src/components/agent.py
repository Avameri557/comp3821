from dataclasses import dataclass, field
import random

# selfish       minimises its own cost
# social        minimises the cost its trip adds for everyone (its own cost
#               plus the delay it causes others)
# controller    selfish, but backs its announcement with fake agents: some copy
#               its route, so its road looks full and others avoid it; with
#               rival controllers, the rest fill the roads that avoid the
#               rivals, pushing traffic onto the rivals' roads
# short_seller  selfish; recognises every fake agent it sees and publishes them
ROLES = ("selfish", "social", "controller", "short_seller")


@dataclass
class Agent:
    agent_id: int
    origin: int
    destination: int
    alpha: float = 1.0
    role: str = "selfish"

    current_node: int = field(init=False)
    route_history: list[int] = field(init=False)
    total_cost: float = field(default=0.0, init=False)
    arrived: bool = field(default=False, init=False)

    def __post_init__(self):
        if not 0 <= self.alpha <= 1:
            raise ValueError("alpha must be between 0 and 1")
        if self.role not in ROLES:
            raise ValueError(f"role must be one of {', '.join(ROLES)}")
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

    def observe_routes(self, intentions, agent=None, ignore=()):
        """The other announcements this agent sees.

        Each other announcement (a whole route: the edges crossed so far plus
        the current plan) is seen independently with probability alpha.
        Announcements whose id is in `ignore` (fake agents the observer knows
        are fake) are skipped.
        """
        return [intention for intention in intentions
                if not (agent is not None and intention["id"] == agent.agent_id)
                and intention["id"] not in ignore
                and self.rng.random() < self.alpha]

    @staticmethod
    def count_edges(seen):
        """K[edge]: announcements seen with `edge` on their route."""
        observed = {}
        for intention in seen:
            route = intention["route"]
            for edge in zip(route, route[1:]):
                observed[edge] = observed.get(edge, 0) + 1
        return observed

    def estimate_load(self, observed, edge, cap=None):
        """Estimated number of *other* agents using `edge`: K / alpha (unbiased).

        cap: if given, the estimate is limited to this many agents (the number
        of other agents in the scenario), so impossible loads are ruled out.
        """
        estimate = observed.get(edge, 0) / self.alpha if self.alpha else 0.0
        return estimate if cap is None else min(estimate, cap)
