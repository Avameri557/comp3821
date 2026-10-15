import networkx as nx
from .edge import Edge

class Network:
    def __init__(self):
        self.graph = nx.DiGraph()

    def add_edge(self, source, target, a, b):
        edge = Edge(source, target, a, b)
        self.graph.add_edge(source, target, edge=edge)

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
