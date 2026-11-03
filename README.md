# COMP3821: routing with partial information

Agent-based simulator for how much agents' information about each other's route choices affects congestion.

Please make a new branch for any new feature, ideally named `category/feature` (e.g. `simulation/automation`), and label commits clearly.

## Model

Each scenario has N = 50 agents travelling from origins to destinations on a directed graph. An edge costs `a + b·x`, where x is the number of agents crossing it in the same step. Every step:

1. Each agent still travelling plans its cheapest path on empty-road costs and announces its next edge.
2. Each agent sees every other agent's announcement independently with probability **α**. It estimates the load on each edge as (announcements seen) / α, adds itself on the edges leaving its current node, and re-plans.
3. All agents move one edge at the same time and pay the edge's cost at that step's load.

Agents only move forwards: they never step to a node closer (in hops) to their own origin and never revisit a node. Set `"forward_only": false` in `config.json` to turn this off. `revision_percentage` in `config.json` sets the share of agents that re-plan in step 2 (100 in every scenario).

## Networks

Each network's congestion slopes are set at or near its worst-case price of anarchy at 50 agents. Diagrams are in `diagrams/`.

| Network | Edges | Wardrop / agent | Optimum / agent | Price of anarchy |
|---|---|---|---|---|
| `pigou` | 1→2→4: `0.02x`; 1→3→4: `1` | 1.000 | 0.750 | 1.333 |
| `braess` | Braess's network with `0.02x` on 1→2 and 3→4, `1` on 1→3 and 2→4, free shortcut 2→3 | 2.000 | 1.500 | 1.333 |
| `diamond` | 4 two-hop routes: `1 + 0.023x`, `1.2 + 0.021x`, `1.4 + 0.018x`, `1.6 + 0.015x`, then `1 + 0.003x` | 2.604 | 2.558 | 1.018 |
| `grid` | 3×3 grid, edges `≈1 + 0.02x` (small offsets 0.01–0.11), free edge 2→3 | 5.193 | 5.131 | 1.012 |
| `sioux_falls` | Real Sioux Falls network: the 28 short links cost `0.5x`, the other 48 links their free-flow time (4–10) | 25.618 | 23.892 | 1.072 |

The benchmarks are static (all agents on the network at once). The simulation can beat the social optimum, because agents only congest each other within the same step.

Sioux Falls origins are nodes 1, 2, 3 and destinations 19, 20, 22, with agents spread over those pairs. Source data: Transportation Networks for Research Core Team, *Transportation Networks for Research*, https://github.com/bstabler/TransportationNetworks (copies in `scenarios/sioux_falls/source/`). The data is for academic research use and must be cited in any publication that uses it.

## Tests

| Test | Who varies | Lines on the chart |
|---|---|---|
| `symmetric` | every agent's α, 0 → 1 | mean cost per agent |
| `others_rising` | one random "informed agent" held at α = 1; every other agent's α 0 → 1 | mean cost per agent, informed agent's cost |
| `informed_rising` | every other agent held at α = 0; the informed agent's α 0 → 1 | mean cost per agent, informed agent's cost |

Each line has a shaded 95% confidence band. Every chart also shows the Wardrop equilibrium and social optimum cost per agent. The three charts for a network share one y-axis range.

```
python -m src.experiments                                    # all networks, all tests
python -m src.experiments --network braess --test symmetric  # one chart
python -m src.experiments --plot-only                        # redraw charts from the CSVs
```

α runs from 0 to 1 in steps of 0.05 (`--step`). Each point averages 50 trials (`--trials`). Trial t uses seed 3821 + t at every α, so points along a line differ only in information.

Output in `results/`:

- `benchmarks.csv`: Wardrop and optimum cost per agent, and the price of anarchy, for every network
- `<network>/<test>.png`: the chart
- `<network>/<test>.csv`: mean cost per agent, informed agent's cost (with 95% confidence intervals) and the benchmarks at every α

## Benchmarks

```
python -m src.benchmarks.frank_wolfe --scenario scenarios/sioux_falls --show-paths
```

This solves for the Wardrop equilibrium and the social optimum with path-based gradient projection (`--method fw` for Frank–Wolfe, which gives the same answer), using the same forward-only rule as the simulation.

## Diagrams

The network diagrams are TikZ (`diagrams/*.tex`, shared styles in `diagrams/common.tex`). To rebuild every PNG at 300 dpi (needs pdflatex and pdftoppm):

```
./diagrams/build.sh
```

## Layout

```
scenarios/<network>/      network.json, agents.json, config.json
src/components/           agents, edges, routing
src/simulation/           simulator and scenario loader
src/benchmarks/           Wardrop equilibrium and social optimum
src/experiments.py        the three tests and their charts
diagrams/                 TikZ sources, build script and PNGs
results/                  test output
```
