import networkx as nx

class SelfishRouting:
    def choose_next_node(self, agent, network, perceived_costs):
        if agent.arrived:
            return None

        path = nx.shortest_path(
            network,
            source=agent.current_node,
            target=agent.destination,
            weight=lambda u, v, data: perceived_costs[(u, v)]
        )

        return path[1] if len(path) > 1 else None
