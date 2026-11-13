"""
Benchmarks for a scenario: the Wardrop equilibrium and the social optimum.

Static, non-atomic traffic assignment: each origin–destination (OD) pair's
agents are a continuous flow, all on the network at once, and an edge with
flow x costs a + b·x. These are reference values for the step-based
simulation, not exact predictions of it.

    Wardrop equilibrium: no agent can lower its cost by switching path
        = minimise  Σ_e ∫_0^{x_e} c_e(s) ds      (Beckmann objective)
    Social optimum: lowest total cost
        = minimise  Σ_e x_e · c_e(x_e)          (marginal cost a + 2b·x)
    Price of anarchy = Wardrop total cost / optimum total cost

Two solvers give the same answer:
    --method paths   path-based gradient projection (default; fast and precise)
    --method fw      Frank–Wolfe with an exact line search

Demand: agents are spread evenly over the reachable source/destination pairs
of agents.json. Paths follow the simulation's rule: with forward_only (the
default) they never step back towards the origin.

Usage:
    python -m src.benchmarks.frank_wolfe --scenario scenarios/braess
    python -m src.benchmarks.frank_wolfe --scenario scenarios/sioux_falls --show-paths
"""

import argparse
import json
import math
from collections import Counter
from pathlib import Path

import networkx as nx
import numpy as np

from src.simulation.scenario_loader import load_scenario


def scenario_demand(scenario):
    """({(origin, destination): agents}, simulation, config) with demand spread evenly over OD pairs."""
    simulation, config = load_scenario(scenario)
    agent_data = json.loads((Path(scenario) / "agents.json").read_text(encoding="utf-8"))
    if "generate" in agent_data:
        spec = agent_data["generate"]
        graph = simulation.network.graph
        pairs = [(o, d) for o in spec["sources"] for d in spec["destinations"]
                 if o != d and nx.has_path(graph, o, d)]
        demand = {pair: spec["count"] / len(pairs) for pair in pairs}
    else:
        demand = dict(Counter((a.origin, a.destination) for a in simulation.agents if a.origin != a.destination))
    return demand, simulation, config


class Solver:
    def __init__(self, network, demand, forward_only=True):
        self.graph = network.graph
        self.edges = list(self.graph.edges)
        self.index = {e: i for i, e in enumerate(self.edges)}
        self.a = np.array([network.get_edge(*e).a for e in self.edges], dtype=float)
        self.b = np.array([network.get_edge(*e).b for e in self.edges], dtype=float)
        self.demand = {od: d for od, d in demand.items() if d > 0}
        self.origins = sorted({o for o, _ in self.demand})
        # Allowed sub-graph per origin (never step back towards the origin)
        self.allowed = {}
        for o in self.origins:
            if forward_only:
                depth = nx.single_source_shortest_path_length(self.graph, o)
                keep = [(u, v) for u, v in self.edges if u in depth and v in depth and depth[v] >= depth[u]]
                self.allowed[o] = self.graph.edge_subgraph(keep)
            else:
                self.allowed[o] = self.graph
        for (o, d) in self.demand:
            if d not in self.allowed[o] or not nx.has_path(self.allowed[o], o, d):
                raise ValueError(f"No allowed path from {o} to {d}")

    def cost(self, x):
        return self.a + self.b * x

    def gradient(self, x, problem):
        """Edge cost (Wardrop) or marginal cost a + 2b·x (optimum)."""
        return self.a + (1 if problem == "ue" else 2) * self.b * x

    def curvature(self, problem):
        return (1 if problem == "ue" else 2) * self.b

    def all_or_nothing(self, edge_cost):
        """Cheapest path per OD under edge_cost: (edge flows, {od: {path: flow}}, Σ demand·path cost)."""
        y = np.zeros(len(self.edges))
        paths, total = {}, 0.0
        weight = lambda u, v, _: edge_cost[self.index[(u, v)]]
        for o in self.origins:
            dist, routes = nx.single_source_dijkstra(self.allowed[o], o, weight=weight)
            for (oo, d), q in self.demand.items():
                if oo != o:
                    continue
                path = tuple(routes[d])
                paths[(o, d)] = {path: q}
                total += q * dist[d]
                for u, v in zip(path, path[1:]):
                    y[self.index[(u, v)]] += q
        return y, paths, total

    def solve_fw(self, problem="ue", tolerance=1e-6, max_iterations=20000):
        """Frank–Wolfe: move towards the all-or-nothing point with an exact line search."""
        x, x_paths, _ = self.all_or_nothing(self.gradient(np.zeros(len(self.edges)), problem))
        gap, iterations = math.inf, 0
        for iterations in range(1, max_iterations + 1):
            g = self.gradient(x, problem)
            y, y_paths, cheapest = self.all_or_nothing(g)
            current = float(x @ g)
            gap = (current - cheapest) / current if current > 0 else 0.0
            if gap < tolerance:
                break
            d = y - x
            slope = float(d @ g)
            if slope >= 0:
                break
            bend = float(d @ (self.curvature(problem) * d))   # the objective is quadratic
            lam = 1.0 if bend <= 0 else min(1.0, -slope / bend)
            x = x + lam * d
            x_paths = {od: {p: f * (1 - lam) for p, f in x_paths[od].items()} for od in x_paths}
            for od, flows in y_paths.items():
                for p, f in flows.items():
                    x_paths[od][p] = x_paths[od].get(p, 0.0) + f * lam
        return self.report(x, x_paths, problem, gap, iterations)

    def solve_paths(self, problem="ue", tolerance=1e-6, max_iterations=20000):
        """Path-based gradient projection (Jayakrishnan et al., 1994).

        Each iteration adds every OD's current cheapest path, then moves flow
        from each dearer path onto it by a Newton step (cost difference /
        curvature of the edges the two paths do not share).
        """
        x = np.zeros(len(self.edges))
        path_flows = {od: {} for od in self.demand}
        path_edges = {}

        def edges_of(path):
            if path not in path_edges:
                path_edges[path] = np.array([self.index[(u, v)] for u, v in zip(path, path[1:])], dtype=int)
            return path_edges[path]

        _, start, _ = self.all_or_nothing(self.gradient(x, problem))
        for od, flows in start.items():
            for path, f in flows.items():
                path_flows[od][path] = f
                x[edges_of(path)] += f

        h = self.curvature(problem)
        gap, iterations = math.inf, 0
        for iterations in range(1, max_iterations + 1):
            g = self.gradient(x, problem)
            _, cheapest_paths, cheapest = self.all_or_nothing(g)
            current = float(x @ g)
            gap = (current - cheapest) / current if current > 0 else 0.0
            if gap < tolerance:
                break
            for od in self.demand:
                best = next(iter(cheapest_paths[od]))
                flows = path_flows[od]
                flows.setdefault(best, 0.0)
                for path in list(flows):
                    if path == best or flows[path] <= 0:
                        continue
                    g = self.gradient(x, problem)
                    pe, be = edges_of(path), edges_of(best)
                    diff = float(g[pe].sum() - g[be].sum())
                    if diff <= 0:
                        continue
                    bend = float(h[np.setxor1d(pe, be)].sum())
                    shift = flows[path] if bend <= 0 else min(flows[path], diff / bend)
                    flows[path] -= shift
                    flows[best] += shift
                    x[pe] -= shift
                    x[be] += shift
                for path in [p for p, f in flows.items() if f <= 1e-12]:
                    del flows[path]
            x = np.maximum(x, 0.0)
        return self.report(x, path_flows, problem, gap, iterations)

    def report(self, x, path_flows, problem, gap, iterations):
        real_cost = self.cost(x)
        total = float(x @ real_cost)
        agents = sum(self.demand.values())
        paths = {}
        for od, flows in path_flows.items():
            used = []
            for p, f in sorted(flows.items(), key=lambda kv: -kv[1]):
                if f > 1e-6 * self.demand[od]:
                    cost = sum(real_cost[self.index[(u, v)]] for u, v in zip(p, p[1:]))
                    used.append({"path": list(p), "flow": f, "cost": float(cost)})
            paths[f"{od[0]}->{od[1]}"] = used
        return {
            "total_cost": total,
            "average_cost": total / agents if agents else 0.0,
            "relative_gap": gap,
            "iterations": iterations,
            "paths": paths,
        }


def solve_scenario(scenario, method="paths", tolerance=1e-8, max_iterations=50000):
    """Wardrop equilibrium, social optimum and price of anarchy for a scenario."""
    demand, simulation, config = scenario_demand(scenario)
    solver = Solver(simulation.network, demand, forward_only=config.get("forward_only", True))
    solve = solver.solve_paths if method == "paths" else solver.solve_fw
    ue = solve("ue", tolerance, max_iterations)
    so = solve("so", tolerance, max_iterations)
    return {
        "agents": sum(demand.values()),
        "wardrop_equilibrium": ue,
        "social_optimum": so,
        "price_of_anarchy": ue["total_cost"] / so["total_cost"] if so["total_cost"] > 0 else math.nan,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--method", choices=["paths", "fw"], default="paths")
    parser.add_argument("--show-paths", action="store_true", help="Print the paths used per OD pair")
    args = parser.parse_args()

    result = solve_scenario(args.scenario, args.method)
    ue, so = result["wardrop_equilibrium"], result["social_optimum"]
    print(f"{args.scenario.name}: {result['agents']:g} agents")
    print(f"  Wardrop equilibrium: total {ue['total_cost']:.4f}   per agent {ue['average_cost']:.4f}")
    print(f"  Social optimum:      total {so['total_cost']:.4f}   per agent {so['average_cost']:.4f}")
    print(f"  Price of anarchy:    {result['price_of_anarchy']:.4f}")
    if args.show_paths:
        for name, res in (("Wardrop equilibrium", ue), ("Social optimum", so)):
            print(f"\n  {name} paths (flow, cost):")
            for od, used in res["paths"].items():
                print(f"    {od}: " + "; ".join(
                    f"{'-'.join(map(str, p['path']))} ({p['flow']:.2f}, {p['cost']:.3f})" for p in used))


if __name__ == "__main__":
    main()
