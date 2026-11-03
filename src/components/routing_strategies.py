import heapq
import math

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

    def choose_timed_path(self, agent, network, timed_cost, depth=None):
        """Cheapest path when an edge's cost depends on when it is crossed.

        timed_cost(u, v, j): cost of crossing edge (u, v) j steps from now
        (every edge takes one step, so a path's j-th edge is crossed j steps
        from now). Searches (node, steps from now) states, with the same
        forward-only rules as choose_path and no node visited twice.
        """
        if agent.arrived:
            return None
        start, target = agent.current_node, agent.destination
        visited = set(agent.route_history)

        def key(v, j, path):
            # Two partial paths reaching v at step j have the same futures if they
            # block the same nodes. Moving forwards, only nodes at v's own depth can
            # still be reached, so only those need to be part of the key.
            if depth is None:
                return v, j, frozenset(path)
            return v, j, frozenset(n for n in path if depth.get(n) == depth.get(v))

        best = {key(start, 0, (start,)): 0.0}
        heap = [(0.0, 0, start, (start,))]
        while heap:
            cost, j, u, path = heapq.heappop(heap)
            if u == target:
                return list(path)
            if cost > best.get(key(u, j, path), math.inf):
                continue
            for v in network.successors(u):
                if v in path:
                    continue
                if depth is not None and (v in visited or depth.get(v, -1) < depth.get(u, -1)):
                    continue
                new_cost = cost + timed_cost(u, v, j)
                new_path = path + (v,)
                k = key(v, j + 1, new_path)
                if new_cost < best.get(k, math.inf):
                    best[k] = new_cost
                    heapq.heappush(heap, (new_cost, j + 1, v, new_path))
        raise nx.NetworkXNoPath(f"No allowed path from {start} to {target}")
