# COMP3821: routing with partial information

Agent-based simulator for how much agents' information about each other's route choices affects congestion.

Please make a new branch for any new feature, ideally named `category/feature` (e.g. `simulation/automation`), and label commits clearly.

## Model

Each scenario has N = 50 agents travelling from origins to destinations on a directed graph. Congestion counts the **whole run**: an edge costs `a + b·x`, where x is the number of agents whose route uses that edge at any point, and each agent pays the cost of every edge on its final route once the run ends. This is the same model as the Wardrop and optimum benchmarks. Every step:

1. Every agent announces its **current route**: the whole route it chose most recently, including the edges it has already crossed. Before an agent's first decision, that is its cheapest path on empty-road costs. Agents that have arrived announce the route they took.
2. Agents still travelling decide **one at a time, in a new random order every step**. When its turn comes, an agent sees every other agent's whole route independently with probability **α**: the revised route for agents that have already decided this step, the announcement for the rest. It estimates each edge's load as (routes seen using that edge) / α, adds itself, and re-plans its cheapest remaining path. Its new route replaces its announcement for the agents after it.
3. All agents still travelling move one edge.

Agents re-plan every step, so only the first edge of any plan is committed. (The `simplified` branch has next-edge announcements with simultaneous decisions, and `simplified_announcing_routes` has timed whole-route announcements with simultaneous decisions. In both, agents only congest each other when they cross an edge in the same step.)

Agents only move forwards: they never step to a node closer (in hops) to their own origin and never revisit a node. Set `"forward_only": false` in `config.json` to turn this off. `revision_percentage` in `config.json` sets the share of agents that re-plan in step 2 (100 in every scenario).

**Capping estimates (optional).** By default an agent's estimate K/α can be any size, so with little information it can believe an edge holds more agents than exist. Set `"cap_estimates": true` in `config.json` (or run the experiments with `--cap`) and agents know how many agents there are: every estimated load is limited to N − 1, the number of other agents. On Pigou this removes every switch to the bottom road, because the top road can then never look worse than it can really be (0.02 × 50 = 1).

## Networks

Each network's congestion slopes are set at or near its worst-case price of anarchy at 50 agents. Diagrams are in `diagrams/`.

| Network | Edges | Wardrop / agent | Optimum / agent | Price of anarchy |
|---|---|---|---|---|
| `pigou` | 1→2→4: `0.02x`; 1→3→4: `1` | 1.000 | 0.750 | 1.333 |
| `braess` | Braess's network with `0.02x` on 1→2 and 3→4, `1` on 1→3 and 2→4, free shortcut 2→3 | 2.000 | 1.500 | 1.333 |
| `diamond` | 4 two-hop routes: `1 + 0.023x`, `1.2 + 0.021x`, `1.4 + 0.018x`, `1.6 + 0.015x`, then `1 + 0.003x` | 2.604 | 2.558 | 1.018 |
| `grid` | 3×3 grid, edges `≈1 + 0.02x` (small offsets 0.01–0.11), free edge 2→3 | 5.193 | 5.131 | 1.012 |
| `sioux_falls` | Real Sioux Falls network: the 28 short links cost `0.5x`, the other 48 links their free-flow time (4–10) | 25.618 | 23.892 | 1.072 |

The simulation uses the same whole-run congestion as the benchmarks, so its cost per agent can be compared with them directly. Small differences remain because the simulation has whole agents and draws each agent's origin–destination pair at random, while the benchmarks spread the demand evenly over the pairs as a continuous flow.

Sioux Falls origins are nodes 1, 2, 3 and destinations 19, 20, 22, with agents spread over those pairs. Source data: Transportation Networks for Research Core Team, *Transportation Networks for Research*, https://github.com/bstabler/TransportationNetworks (copies in `scenarios/sioux_falls/source/`). The data is for academic research use and must be cited in any publication that uses it.

## Tests

| Test | Who varies | Lines on the chart |
|---|---|---|
| `symmetric` | every agent's α, 0 → 1 | mean cost per agent |
| `others_rising` | one random "informed agent" held at α = 1; every other agent's α 0 → 1 | mean cost per agent, informed agent's cost |
| `informed_rising` | every other agent held at α = 0; the informed agent's α 0 → 1 | mean cost per agent, informed agent's cost |
| `informed_rising_half` | every other agent held at α = 0.5; the informed agent's α 0 → 1 | mean cost per agent, informed agent's cost |

Each line has a shaded 95% confidence band. Every chart also shows the Wardrop equilibrium and social optimum cost per agent. Each chart's y-axis is fitted to its own lines, bands and reference lines.

```
python -m src.experiments                                    # all networks, all four tests
python -m src.experiments --network braess --test symmetric  # one chart
python -m src.experiments --plot-only                        # redraw charts from the CSVs
python -m src.experiments --cap                              # agents cap estimates at N - 1
```

α runs from 0 to 1 in steps of 0.05 (`--step`). Each point averages 200 trials (`--trials`). Trial t uses seed 3821 + t at every α, so points along a line differ only in information.

Output in `results/` (or `results_capped/` with `--cap`):

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
src/experiments.py        the four tests and their charts
diagrams/                 TikZ sources, build script and PNGs
results/                  test output
results_capped/           test output with capped estimates
```
