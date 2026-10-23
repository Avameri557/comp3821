# Background

Simulator for 3821 project.

Please make a new branch for any new features, ideally with the naming convention `category/feature` i.e. `simulation/automation` and label commits clearly.

# Network Loading Guide

## Simulation v1
Import agents, networks and configuration JSONs according to the ```example``` and ```generated``` template. 

To run manual simulation, run: 
`python -m src.simulation.runner --scenario scenarios/<scenario-name> --output results/<scenario-name>`

To run stage 1 symmetric tests, run:
```
python -m src.simulation.symmetric_sweep \
        --scenario scenarios/<scenario-name> \
        --output results/<scenario-name> \
        --trials <how many times to repeat> \
        --alpha-step <alpha interval>
```

## Agent movement

Agents only move forwards. At every step an agent may only take an edge `(u, v)` where `v` is at least as many hops from the agent's own origin as `u` (it never steps back towards where it started), and it never returns to a node it has already visited. This applies to both the initial plan and the reconsidered plan, so every agent reaches its destination in at most as many steps as there are nodes. Sideways moves are allowed (e.g. the 2 → 3 shortcut in Braess).

Set `"forward_only": false` in a scenario's `config.json` to let agents move freely again (the original behaviour, in which groups of agents can bounce back and forth indefinitely).

## Cascade mode (heats)

Instead of one batch of agents, a scenario can release its agents in **heats**, one after another, into the same graph. Add to `config.json`:

```
"cascade": {"heats": 20, "heat_interval": 1}
```

- `agents.json` describes **one heat**; it is repeated `heats` times (with fresh random origin/destination draws for `generate`), so the total is `heats × count` agents.
- A new heat is released every `heat_interval` timesteps. Heats overlap: every released agent shares the roads and congests the others.
- **Edge memory.** Every edge remembers the cost it had the last time any agent crossed it (edges never used show their base cost `a`).
- **What agents see.** The initial plan still uses base costs. When reconsidering, an agent prices each edge in this order:
  1. if it saw at least one other agent announce that edge → estimate from announcements, `a + b·(K/α (+1 on edges leaving its node))`;
  2. otherwise, if it sees the edge's previous cost (each edge independently with probability α) → that previous cost;
  3. otherwise → base cost `a` (+ `b` for itself on edges leaving its node).

  So α controls both seeing other agents' announcements and seeing previous edge costs, with separate random draws.
- Scenarios without `cascade` behave exactly as before.

Example scenarios: `scenarios/braess_cascade` (20 heats of 20 agents) and `scenarios/sioux_falls_cascade` (20 heats of 100 agents). Every tool works on them (`runner`, `symmetric_sweep`, `animate_run`, `information_plot`); `results.json` gains a `heats` list with the average cost of each heat, overall and per α. The viewer shows agents waiting at their origins until their heat is released.

To see how cost develops from heat to heat:

```
# whole populations compared: everyone blind / half / fully informed
python -m src.visualisation.cascade_plot --scenario scenarios/braess_cascade \
        --population 0 --population 0.5 --population 1

# mixed population: 30% fully informed, the rest blind, each group plotted separately
python -m src.visualisation.cascade_plot --scenario scenarios/braess_cascade --population 1:0.3,0
```

Options: `--trials` seeds per population (default 20), `--workers`, `--output` (default `results/<scenario>_cascade/`, with `plot.png`, `summary.csv`, `raw_results.csv`).

## Sioux Falls scenario

`scenarios/sioux_falls` uses the real Sioux Falls nodes and links (24 nodes, 76 directed links), written in the same style as the Pigou and Braess scenarios:

```
c_e(f) = a_e + b_e * f        # f = number of agents on e in this timestep
a_e = the link's free-flow time from the Sioux Falls data (2 to 10)
b_e = 0.01 for every edge
```

Capacities are not used. Edit `network.json` directly to change any edge's `a` or `b`.

Demand is our own, not the TNTP OD matrix: origins are the 4 westernmost nodes (1, 3, 12, 13) and destinations are the nodes at maximum hop depth from that set (7, 18, 19, found by BFS). Agents are spread uniformly over those origin–destination pairs. `network.json` also stores each node's real longitude/latitude under `coordinates` (for plotting only; the simulator ignores it).

To regenerate the scenario (e.g. a different agent count, side or congestion level):

```
python -m src.tools.build_sioux_falls --output scenarios/sioux_falls \
        --agents 1000 --b 0.01 --alpha 1.0 --side west
```

Re-running the generator overwrites `network.json`, so copy the folder first if you have edited it by hand. `--b` sets the slope given to every edge. `--cost bpr` writes the original capacity-based BPR costs instead (`"type": "bpr"` edges, with `--vehicles-per-agent` saved to `config.json` and applied at load time).

Source data: Transportation Networks for Research Core Team, *Transportation Networks for Research*, https://github.com/bstabler/TransportationNetworks (copies in `scenarios/sioux_falls/source/`). The data is for academic research use and must be cited in any publication that uses it.

## Visualisation

Two tools in `src/visualisation/`. Both take an information mix ("population") written as `alpha[:share]` groups:
`1` = every agent has α = 1, `0.5` = every agent has α = 0.5, `1:0.2,0` = 20% of agents have α = 1 and the rest α = 0 (assigned at random, independent of origin/destination). Without one, the α values in `agents.json` are used.

### Watch a run

```
python -m src.visualisation.animate_run --scenario scenarios/braess \
        --population 0 --population 0.5 --population 1 --population 1:0.25,0
```

Each `--population` adds a side-by-side panel (same scenario and seed), so you can compare information levels directly. Vertices are drawn with origins in green and destinations in red; agents travel along edges in groups, sized by how many agents are in them and coloured by α; edges are shaded by how many agents use them in the current step. Below each panel: the step, how many agents have arrived, the average cost so far, and the final average cost per α group.

Controls: Play/Pause (or space), left/right arrows to step, drag the slider to scrub.
Add `--save results/braess_demo.gif` (or `.mp4`) to export an animation, `--snapshot 1.5 results/braess.png` for a still image, and `--no-show` to skip the window. Graphs without coordinates are laid out left to right by distance from the origins; Sioux Falls uses its real map coordinates.

### Graph travel time against information

```
# everyone has the same α: average travel cost and steps to arrive vs α
python -m src.visualisation.information_plot --scenario scenarios/braess

# mixed population: cost of α=1 agents vs α=0 agents as the share of α=1 agents grows
python -m src.visualisation.information_plot --scenario scenarios/braess --mixed 1 0
```

Options: `--trials` seeds per point (default 20), `--step` spacing of α or share values (default 0.05), `--workers` parallel processes. Each point uses the same seeds, bands are 95% confidence intervals, and red crosses mark points where some runs hit the step limit. Output goes to `results/<scenario>_information[...]/` as `plot.png`, `summary.csv` and `raw_results.csv`. Sioux Falls (1000 agents) takes about a second per run, so use fewer trials or a coarser step there.
