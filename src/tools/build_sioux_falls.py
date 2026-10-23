"""
Build the Sioux Falls scenario from the TNTP source files.

Source data: Transportation Networks for Research Core Team,
https://github.com/bstabler/TransportationNetworks (SiouxFalls folder).
A copy of the files lives in scenarios/sioux_falls/source/.

Network: the real Sioux Falls nodes and 76 directed links, written in the
same style as the Pigou and Braess scenarios. Edge costs are linear in the
number of agents f on the edge (default, --cost linear):
    c_e(f) = a_e + b * f
    a_e = the link's free-flow time (2 to 10)
    b   = one congestion slope for every edge (--b, default 0.01)
Capacities are not used. Edit network.json by hand to give edges their own b.
--cost bpr writes the original capacity-based BPR costs instead.

Demand is our own (not the TNTP OD matrix):
    origins      = a set of vertices on one side of the network
                   (default: the 4 westernmost nodes, by coordinates)
    destinations = the vertices at maximum hop depth from the origin set
                   (multi-source BFS)
Agents are spread uniformly over the reachable origin/destination pairs
by the existing "generate" option in agents.json.

Usage:
    python -m src.tools.build_sioux_falls \
        --output scenarios/sioux_falls \
        --agents 1000 --b 0.01 --alpha 1.0
"""

import argparse
import json
from collections import deque
from pathlib import Path

SOURCE_DIR = Path("scenarios/sioux_falls/source")


def read_tntp_rows(path):
    """Yield the data rows of a TNTP file as lists of strings (no ';')."""
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        parts = line.replace(";", " ").split()
        # Metadata ("<...>") and header ("~ ...") lines never start with a number.
        if parts and parts[0].isdigit():
            yield parts


def read_links(source_dir):
    links = []
    for p in read_tntp_rows(source_dir / "SiouxFalls_net.tntp"):
        # init_node term_node capacity length free_flow_time b power speed toll link_type
        links.append({
            "from": int(p[0]),
            "to": int(p[1]),
            "capacity": float(p[2]),
            "length": float(p[3]),
            "free_flow_time": float(p[4]),
            "alpha": float(p[5]),
            "beta": float(p[6]),
        })
    return links


def read_coordinates(source_dir):
    return {
        int(p[0]): (float(p[1]), float(p[2]))
        for p in read_tntp_rows(source_dir / "SiouxFalls_node.tntp")
    }


def farthest_by_hops(nodes, links, origins):
    """Multi-source BFS over directed links; return (depth, nodes at max depth)."""
    succ = {n: [] for n in nodes}
    for link in links:
        succ[link["from"]].append(link["to"])
    depth = {o: 0 for o in origins}
    queue = deque(origins)
    while queue:
        u = queue.popleft()
        for v in succ[u]:
            if v not in depth:
                depth[v] = depth[u] + 1
                queue.append(v)
    max_depth = max(depth.values())
    return max_depth, sorted(n for n, d in depth.items() if d == max_depth)


def number(x):
    """6.0 -> 6, so the JSON reads like the hand-written scenarios."""
    return int(x) if float(x).is_integer() else x


def edge_cost(link, cost, b):
    t0, cap = link["free_flow_time"], link["capacity"]
    if cost == "linear":
        return {"type": "linear", "a": number(t0), "b": number(b)}
    if cost == "bpr":
        return {
            "type": "bpr",
            "free_flow_time": t0,
            "capacity": cap,
            "alpha": link["alpha"],
            "beta": link["beta"],
        }
    raise ValueError(f"Unknown cost model {cost!r}")


def network_json(nodes, edges, coords):
    """Format like scenarios/pigou/network.json, plus node map coordinates
    (only used by the visualiser; delete them for a left-to-right layout)."""
    lines = ["{", f'  "nodes": {json.dumps(nodes)},', '  "edges": [']
    for i, edge in enumerate(edges):
        comma = "," if i < len(edges) - 1 else ""
        lines += [
            "    {",
            f'      "from": {edge["from"]}, "to": {edge["to"]},',
            f'      "cost": {json.dumps(edge["cost"])}',
            "    }" + comma,
        ]
    lines.append("  ],")
    lines.append('  "coordinates": {')
    for i, n in enumerate(nodes):
        comma = "," if i < len(nodes) - 1 else ""
        lines.append(f'    "{n}": [{coords[n][0]}, {coords[n][1]}]{comma}')
    lines += ["  }", "}"]
    return "\n".join(lines) + "\n"


def build(output, agents, alpha, b=0.01, cost="linear", vehicles_per_agent=200, origins=None,
          side="west", seed=42, revision_percentage=100, max_timesteps=200, source_dir=SOURCE_DIR):
    source_dir = Path(source_dir)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)

    links = read_links(source_dir)
    coords = read_coordinates(source_dir)
    nodes = sorted(coords)

    if origins is None:
        # Pick the 4 nodes furthest towards the chosen side.
        key = {
            "west": lambda n: coords[n][0],
            "east": lambda n: -coords[n][0],
            "south": lambda n: coords[n][1],
            "north": lambda n: -coords[n][1],
        }[side]
        origins = sorted(sorted(nodes, key=key)[:4])

    depth, destinations = farthest_by_hops(nodes, links, origins)

    edges = [
        {"from": link["from"], "to": link["to"], "cost": edge_cost(link, cost, b)}
        for link in links
    ]
    agents_spec = {
        "generate": {
            "count": agents,
            "sources": origins,
            "destinations": destinations,
            "alpha": alpha,
        }
    }
    config = {
        "max_timesteps": max_timesteps,
        "record_history": True,
        "seed": seed,
        "revision_percentage": revision_percentage,
        "forward_only": True,
    }
    if cost == "bpr":
        # Linear costs already include the scale in b_e; BPR scales at load time.
        config["vehicles_per_agent"] = (
            int(vehicles_per_agent) if float(vehicles_per_agent).is_integer() else vehicles_per_agent
        )

    (output / "network.json").write_text(network_json(nodes, edges, coords), encoding="utf-8")
    for name, data in (("agents.json", agents_spec), ("config.json", config)):
        (output / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    return {"origins": origins, "destinations": destinations, "hop_depth": depth,
            "links": len(links), "nodes": len(nodes)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("scenarios/sioux_falls"))
    parser.add_argument("--source", type=Path, default=SOURCE_DIR)
    parser.add_argument("--agents", type=int, default=1000)
    parser.add_argument("--alpha", type=float, default=1.0)
    parser.add_argument("--b", type=float, default=0.01,
                        help="Congestion slope given to every edge (linear costs)")
    parser.add_argument("--vehicles-per-agent", type=float, default=200,
                        help="Only for --cost bpr: real vehicles per simulated agent")
    parser.add_argument("--cost", choices=["linear", "bpr"], default="linear")
    parser.add_argument("--origins", type=int, nargs="+", default=None,
                        help="Origin node ids (default: 4 nodes on --side)")
    parser.add_argument("--side", choices=["west", "east", "north", "south"], default="west")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--revision-percentage", type=float, default=100)
    parser.add_argument("--max-timesteps", type=int, default=200)
    args = parser.parse_args()

    info = build(
        output=args.output, agents=args.agents, alpha=args.alpha,
        b=args.b, cost=args.cost, vehicles_per_agent=args.vehicles_per_agent, origins=args.origins,
        side=args.side, seed=args.seed, revision_percentage=args.revision_percentage,
        max_timesteps=args.max_timesteps, source_dir=args.source,
    )
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
