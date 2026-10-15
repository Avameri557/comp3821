import pytest
import networkx as nx

from src.networks.network import Network, Edge

def test_edge_cost():
    edge = Edge(1, 2, a=5, b=2)

    assert edge.cost() == 5
    assert edge.cost(3) == 11


def test_directed_edges():
    network = Network()
    network.add_edge(1, 2, a=5, b=1)

    assert network.graph.has_edge(1, 2)
    assert not network.graph.has_edge(2, 1)


def test_shortest_path():
    network = Network()

    network.add_edge(1, 2, 2, 1)
    network.add_edge(2, 4, 2, 1)
    network.add_edge(1, 3, 3, 0.2)
    network.add_edge(3, 4, 3, 0.2)

    assert network.shortest_path(1, 4) == [1, 2, 4]

    network.get_edge(1, 2).flow = 5
    network.get_edge(2, 4).flow = 5

    assert network.shortest_path(1, 4) == [1, 3, 4]


def test_total_cost():
    network = Network()
    network.add_edge(1, 2, 5, 2)

    network.get_edge(1, 2).flow = 3

    assert network.total_cost() == 33


def test_unreachable_destination():
    network = Network()
    network.add_edge(1, 2, 5, 1)
    network.add_edge(3, 4, 5, 1)

    with pytest.raises(nx.NetworkXNoPath):
        network.shortest_path(1, 4)
