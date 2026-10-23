import networkx as nx
from dataclasses import dataclass

@dataclass
class Edge:
    source: int
    target: int
    a: float
    b: float
    flow: float = 0.0
    # "linear": cost = a + b * flow   (a -> base cost, b -> flow sensitivity)
    # "bpr":    cost = a * (1 + b * (flow / capacity) ** power)
    #           (a -> free-flow time, b -> BPR alpha, usually 0.15, power usually 4)
    kind: str = "linear"
    capacity: float | None = None
    power: float = 4.0

    def __post_init__(self):
        if self.kind not in ("linear", "bpr"):
            raise ValueError(f"Unknown edge cost type {self.kind!r}")
        if self.kind == "bpr" and not (self.capacity and self.capacity > 0):
            raise ValueError("BPR edges need a positive capacity")

    def cost(self, flow=None):
        if flow is None:
            flow = self.flow
        if self.kind == "bpr":
            return self.a * (1 + self.b * (flow / self.capacity) ** self.power)
        # Congestion Cost function, a -> base cost, b -> flow sensitivity, f -> current flow
        return self.a + self.b * flow

class Network:
    def __init__(self):
        self.graph = nx.DiGraph()

    def add_edge(self, source, target, a, b, kind="linear", capacity=None, power=4.0):
        edge = Edge(source, target, a, b, kind=kind, capacity=capacity, power=power)
        self.graph.add_edge(source, target, edge=edge)

    def add_bpr_edge(self, source, target, free_flow_time, capacity, alpha=0.15, beta=4.0):
        self.add_edge(source, target, a=free_flow_time, b=alpha,
                      kind="bpr", capacity=capacity, power=beta)

    def get_edge(self, source, target):
        return self.graph[source][target]["edge"]

    def shortest_path(self, origin, destination):
        return nx.shortest_path(
            self.graph,
            origin,
            destination,
            weight=lambda u, v, data: data["edge"].cost()
        )

    def path_cost(self, path):
        return sum(
            self.get_edge(u, v).cost()
            for u, v in zip(path, path[1:])
        )

    def total_cost(self):
        return sum(
            data["edge"].flow * data["edge"].cost()
            for _, _, data in self.graph.edges(data=True)
        )
