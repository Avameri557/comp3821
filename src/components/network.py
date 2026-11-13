from dataclasses import dataclass

import networkx as nx


@dataclass
class Edge:
    """Linear edge: cost = a + b * flow (flow = agents whose route uses the edge)."""
    source: int
    target: int
    a: float
    b: float
    flow: float = 0.0

    def cost(self, flow=None):
        return self.a + self.b * (self.flow if flow is None else flow)


class Network:
    def __init__(self):
        self.graph = nx.DiGraph()

    def add_edge(self, source, target, a, b):
        self.graph.add_edge(source, target, edge=Edge(source, target, a, b))

    def get_edge(self, source, target):
        return self.graph[source][target]["edge"]
