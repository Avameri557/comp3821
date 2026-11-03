import networkx as nx


class SelfishRouting:
    def choose_path(self, agent, network, costs, depth=None):
        """Cheapest path (list of nodes) from the agent's current node to its destination.

        depth: optional {node: hop distance from the agent's origin}. When given,
        agents only move forwards: every edge (u, v) on the path must have
        depth[v] >= depth[u] (never back towards the origin), and the path may
        not revisit a node the agent has already been to.
        """
        if agent.arrived:
            return None

        if depth is None:
            def weight(u, v, data):
                return costs[(u, v)]
        else:
            visited = set(agent.route_history)

            def weight(u, v, data):
                if v in visited or depth.get(v, -1) < depth.get(u, -1):
                    return None  # networkx treats None as "edge not usable"
                return costs[(u, v)]

        return nx.shortest_path(network, source=agent.current_node, target=agent.destination, weight=weight)
