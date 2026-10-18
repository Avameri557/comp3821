from dataclasses import dataclass, field

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

    def move(self, next_node: int, cost: float):
        self.current_node = next_node
        self.route_history.append(next_node)
        self.total_cost += cost

        if self.current_node == self.destination:
            self.arrived = True


class InformationModel:
    def __init__(self, alpha=1.0):
        if not 0 <= alpha <= 1:
            raise ValueError("alpha must be between 0 and 1")
        self.alpha = alpha

    def get_perceived_costs(self, network):
        # To be updated with better information function
        return {
            (u, v): data["edge"].cost(flow=0)
                    + self.alpha * data["edge"].cost()
            for u, v, data in network.graph.edges(data=True)
        }
