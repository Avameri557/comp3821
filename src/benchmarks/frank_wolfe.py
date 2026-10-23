"""
Frank–Wolfe benchmarks: Wardrop user equilibrium (UE) and social optimum (SO)
for a scenario's network and origin–destination demand.

Static, non-atomic traffic assignment: demand is a continuous flow of agents,
and an edge with flow x costs c_e(x) (a_e + b_e·x for linear edges, BPR also
supported). Every agent of an origin–destination (OD) pair is on the network
at the same time, so these are reference values for the step-based
simulation, not exact predictions of it.

    UE: no agent can lower its cost by switching path
        = minimise  Σ_e ∫_0^{x_e} c_e(s) ds          (Beckmann objective)
    SO: lowest total cost
        = minimise  Σ_e x_e · c_e(x_e)
          (Frank–Wolfe on the marginal cost c_e(x) + x·c_e'(x), = a + 2b·x for linear)
    Price of anarchy (PoA) = total cost at UE / total cost at SO

Algorithm (both problems), Frank–Wolfe (--method fw, default):
    1. all-or-nothing: send each OD's demand along its cheapest path at zero flow
    2. repeat: cost every edge at the current flows (UE: c_e, SO: marginal cost),
       send each OD's demand along its cheapest path (all-or-nothing point y),
       line search for the step λ in [0, 1] minimising the objective along
       x + λ(y - x), update the flows, until the relative gap < --tolerance.
    Frank–Wolfe gets close quickly but converges slowly near the solution.
    --method paths (path-based gradient projection) reaches the same answer to
    much higher precision in a fraction of the time; use it to check FW.
    relative gap = (Σ x·c(x) - Σ demand × cheapest path cost) / Σ x·c(x)
    (with marginal costs for SO); 0 means exactly at equilibrium / optimum.

Demand: by default one heat of agents.json. For "generate", the agents are
spread evenly over the reachable source/destination pairs (the expected
demand); --demand sampled uses the exact pairs drawn with the scenario seed.
Paths follow the same rule as the simulation: if forward_only is on (the
default), agents never step back towards their origin.

Usage:
    python -m src.benchmarks.frank_wolfe --scenario scenarios/braess
    python -m src.benchmarks.frank_wolfe --scenario scenarios/sioux_falls --show-paths
    python -m src.benchmarks.frank_wolfe --scenario scenarios/sioux_falls --demand sampled --seed 3821
"""

import argparse
import json
import math
from collections import Counter
from pathlib import Path

import networkx as nx
import numpy as np

from src.simulation.scenario_loader import load_scenario


# --------------------------------------------------------------------------- demand

def scenario_demand(scenario, mode="expected", seed=None):
    """{(origin, destination): number of agents} for one heat, plus the loaded simulation."""
    simulation, config = load_scenario(scenario, seed=seed)
    one_heat = [a for a in simulation.agents if a.heat == 0]
    agent_data = json.loads((Path(scenario) / "agents.json").read_text(encoding="utf-8"))
    if mode == "expected" and "generate" in agent_data:
        spec = agent_data["generate"]
        graph = simulation.network.graph
        pairs = [
            (o, d) for o in spec["sources"] for d in spec["destinations"]
            if o != d and nx.has_path(graph, o, d)
        ]
        demand = {pair: spec["count"] / len(pairs) for pair in pairs}
    else:
        demand = dict(Counter((a.origin, a.destination) for a in one_heat if a.origin != a.destination))
    return demand, simulation, config


# --------------------------------------------------------------------------- edge functions

class EdgeCosts:
    """Vectorised costs for all edges (linear a + b·x, or BPR)."""

    def __init__(self, network, edges):
        objs = [network.get_edge(*e) for e in edges]
        self.bpr = np.array([o.kind == "bpr" for o in objs])
        self.a = np.array([o.a for o in objs], dtype=float)          # base cost / free-flow time
        self.b = np.array([o.b for o in objs], dtype=float)          # slope / BPR alpha
        self.cap = np.array([o.capacity or 1.0 for o in objs], dtype=float)
        self.power = np.array([o.power for o in objs], dtype=float)
        self.all_linear = not self.bpr.any()

    def cost(self, x):
        lin = self.a + self.b * x
        if self.all_linear:
            return lin
        bpr = self.a * (1 + self.b * (x / self.cap) ** self.power)
        return np.where(self.bpr, bpr, lin)

    def marginal(self, x):
        """d/dx of x·c(x): the cost an extra agent adds for everyone."""
        lin = self.a + 2 * self.b * x
        if self.all_linear:
            return lin
        bpr = self.a * (1 + self.b * (self.power + 1) * (x / self.cap) ** self.power)
        return np.where(self.bpr, bpr, lin)

    def gradient(self, x, problem):
        return self.cost(x) if problem == "ue" else self.marginal(x)

    def hessian(self, x, problem):
        """Diagonal second derivative of the objective (curvature, used by --method paths)."""
        k = 1 if problem == "ue" else 2
        lin = k * self.b
        if self.all_linear:
            return lin
        r = np.maximum(x, 0) / self.cap
        dcost = self.a * self.b * self.power * r ** np.maximum(self.power - 1, 0) / self.cap
        bpr = dcost if problem == "ue" else (self.power + 1) * dcost
        return np.where(self.bpr, bpr, lin)


# --------------------------------------------------------------------------- solver

class FrankWolfe:
    """Frank–Wolfe (and a path-based alternative) with path bookkeeping."""

    def __init__(self, network, demand, forward_only=True):
        self.graph = network.graph
        self.edges = list(self.graph.edges)
        self.index = {e: i for i, e in enumerate(self.edges)}
        self.c = EdgeCosts(network, self.edges)
        self.demand = {od: d for od, d in demand.items() if d > 0}
        self.origins = sorted({o for o, _ in self.demand})
        # Allowed sub-graph per origin (never step back towards the origin)
        self.allowed = {}
        for o in self.origins:
            if forward_only:
                depth = nx.single_source_shortest_path_length(self.graph, o)
                keep = [(u, v) for u, v in self.edges
                        if u in depth and v in depth and depth[v] >= depth[u]]
                self.allowed[o] = self.graph.edge_subgraph(keep)
            else:
                self.allowed[o] = self.graph
        for (o, d) in self.demand:
            if d not in self.allowed[o] or not nx.has_path(self.allowed[o], o, d):
                raise ValueError(f"No allowed path from {o} to {d}")

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

    def line_search(self, x, d, problem):
        """Step λ in [0, 1] minimising the objective along x + λ·d."""
        g0 = float(d @ self.c.gradient(x, problem))
        if g0 >= 0:
            return 0.0
        if self.c.all_linear:
            curvature = float(d @ (self.c.hessian(x, problem) * d))  # objective is quadratic
            return 1.0 if curvature <= 0 else min(1.0, -g0 / curvature)
        slope = lambda lam: float(d @ self.c.gradient(x + lam * d, problem))
        if slope(1.0) <= 0:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (lo, mid) if slope(mid) > 0 else (mid, hi)
        return (lo + hi) / 2

    @staticmethod
    def mix(p, q, weight_p):
        """weight_p·p + (1-weight_p)·q for {od: {path: flow}}."""
        out = {}
        for od in p:
            flows = {path: f * weight_p for path, f in p[od].items()}
            for path, f in q[od].items():
                flows[path] = flows.get(path, 0.0) + f * (1 - weight_p)
            out[od] = {path: f for path, f in flows.items() if f > 1e-12}
        return out

    def solve(self, problem="ue", tolerance=1e-6, max_iterations=20000):
        """Frank–Wolfe with an exact line search (bisection for BPR edges)."""
        x, x_paths, _ = self.all_or_nothing(self.c.gradient(np.zeros(len(self.edges)), problem))
        gap, iterations = math.inf, 0
        for iterations in range(1, max_iterations + 1):
            g = self.c.gradient(x, problem)
            y, y_paths, cheapest = self.all_or_nothing(g)
            current = float(x @ g)
            gap = (current - cheapest) / current if current > 0 else 0.0
            if gap < tolerance:
                break
            lam = self.line_search(x, y - x, problem)
            if lam <= 0:
                break
            x = x + lam * (y - x)
            x_paths = self.mix(y_paths, x_paths, lam)
        return self.report(x, x_paths, problem, gap, iterations)

    def solve_paths(self, problem="ue", tolerance=1e-6, max_iterations=20000):
        """Path-based gradient projection (Jayakrishnan et al., 1994).

        Keeps the paths each OD pair uses. Each iteration adds every OD's
        current cheapest path, then moves flow from each dearer path onto it by
        a Newton step (cost difference / curvature of the edges the paths do not
        share). Converges much faster than Frank–Wolfe near the solution.
        """
        n = len(self.edges)
        x = np.zeros(n)
        path_flows = {od: {} for od in self.demand}
        path_edges = {}

        def edges_of(path):
            if path not in path_edges:
                path_edges[path] = np.array([self.index[(u, v)] for u, v in zip(path, path[1:])], dtype=int)
            return path_edges[path]

        # start: all-or-nothing at zero flow
        _, start, _ = self.all_or_nothing(self.c.gradient(x, problem))
        for od, flows in start.items():
            for path, f in flows.items():
                path_flows[od][path] = f
                x[edges_of(path)] += f

        gap, iterations = math.inf, 0
        for iterations in range(1, max_iterations + 1):
            g = self.c.gradient(x, problem)
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
                    g = self.c.gradient(x, problem)
                    h = self.c.hessian(x, problem)
                    pe, be = edges_of(path), edges_of(best)
                    diff = float(g[pe].sum() - g[be].sum())
                    if diff <= 0:
                        continue
                    only = np.setxor1d(pe, be)
                    curvature = float(h[only].sum())
                    shift = flows[path] if curvature <= 0 else min(flows[path], diff / curvature)
                    flows[path] -= shift
                    flows[best] += shift
                    x[pe] -= shift
                    x[be] += shift
                for path in [p for p, f in flows.items() if f <= 1e-12]:
                    del flows[path]
            x = np.maximum(x, 0.0)
        return self.report(x, path_flows, problem, gap, iterations)

    def report(self, x, path_flows, problem, gap, iterations):
        real_cost = self.c.cost(x)
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
            "problem": "wardrop_equilibrium" if problem == "ue" else "social_optimum",
            "total_cost": total,
            "average_cost": total / agents if agents else 0.0,
            "relative_gap": gap,
            "iterations": iterations,
            "edge_flows": [
                {"from": u, "to": v, "flow": float(x[i]), "cost": float(real_cost[i])}
                for i, (u, v) in enumerate(self.edges) if x[i] > 1e-9
            ],
            "paths": paths,
        }


def solve_scenario(scenario, demand_mode="expected", seed=None, tolerance=1e-6, max_iterations=20000,
                   forward_only=None, method="fw"):
    demand, simulation, config = scenario_demand(scenario, demand_mode, seed)
    if forward_only is None:
        forward_only = config.get("forward_only", True)
    solver = FrankWolfe(simulation.network, demand, forward_only=forward_only)
    solve = solver.solve if method == "fw" else solver.solve_paths
    ue = solve("ue", tolerance, max_iterations)
    so = solve("so", tolerance, max_iterations)
    return {
        "scenario": str(scenario),
        "demand_mode": demand_mode,
        "method": method,
        "forward_only": forward_only,
        "agents": sum(demand.values()),
        "demand": {f"{o}->{d}": q for (o, d), q in demand.items()},
        "wardrop_equilibrium": ue,
        "social_optimum": so,
        "price_of_anarchy": ue["total_cost"] / so["total_cost"] if so["total_cost"] > 0 else math.nan,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--demand", choices=["expected", "sampled"], default="expected",
                        help="expected: agents spread evenly over OD pairs; sampled: the pairs drawn with the seed")
    parser.add_argument("--seed", type=int, default=None, help="Seed for --demand sampled (default: config seed)")
    parser.add_argument("--tolerance", type=float, default=1e-5, help="Stop when the relative gap is below this")
    parser.add_argument("--max-iterations", type=int, default=50000)
    parser.add_argument("--method", choices=["fw", "paths"], default="fw",
                        help="fw: Frank–Wolfe; paths: path-based gradient projection (faster, more precise)")
    parser.add_argument("--free-movement", action="store_true",
                        help="Allow paths that step back towards the origin (as forward_only: false)")
    parser.add_argument("--show-paths", action="store_true", help="Print the paths used per OD pair")
    parser.add_argument("--output", type=Path, default=None, help="Save the full result as JSON")
    args = parser.parse_args()

    result = solve_scenario(
        args.scenario, args.demand, args.seed, args.tolerance, args.max_iterations,
        forward_only=False if args.free_movement else None, method=args.method,
    )
    ue, so = result["wardrop_equilibrium"], result["social_optimum"]
    print(f"{args.scenario.name}: {result['agents']:g} agents over {len(result['demand'])} OD pairs "
          f"({result['demand_mode']} demand, {'forward-only' if result['forward_only'] else 'free'} paths)")
    print(f"  Wardrop equilibrium: total cost {ue['total_cost']:.4f}   average per agent {ue['average_cost']:.4f}"
          f"   (gap {ue['relative_gap']:.1e}, {ue['iterations']} iterations)")
    print(f"  Social optimum:      total cost {so['total_cost']:.4f}   average per agent {so['average_cost']:.4f}"
          f"   (gap {so['relative_gap']:.1e}, {so['iterations']} iterations)")
    print(f"  Price of anarchy:    {result['price_of_anarchy']:.4f}")
    if args.show_paths:
        for name, res in (("Wardrop equilibrium", ue), ("Social optimum", so)):
            print(f"\n  {name} paths (flow, cost):")
            for od, used in res["paths"].items():
                print(f"    {od}: " + "; ".join(
                    f"{'-'.join(map(str, p['path']))} ({p['flow']:.2f}, {p['cost']:.3f})" for p in used))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"\nSaved to {args.output}")


if __name__ == "__main__":
    main()
