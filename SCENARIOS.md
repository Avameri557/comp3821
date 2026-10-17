# Automated scenario runner

Run from the repository root after installing `environment.yaml`:

```bash
python run.py --scenario scenarios/example
pytest -q
```

A scenario directory contains `network.json`, `agents.json`, and optionally `config.json`.

- `network.json`: `{"nodes":[1,2],"edges":[{"from":1,"to":2,"cost":{"type":"linear","a":2,"b":1}}]}`
- `agents.json`: `{"agents":[{"id":0,"origin":1,"destination":2,"alpha":1.0}]}`
- `config.json`: `{"max_timesteps":10000,"record_history":false,"output_directory":"results/example"}`

Costs follow the **existing repository convention** `cost = a + b * flow` (not `a*flow+b`).
Agents make simultaneous decisions and traverse one whole edge per timestep. Edge cost
is charged to the agent, but does **not** determine the number of timesteps spent
traversing an edge. Therefore this is a discrete routing-game prototype, not a
physical traffic-time simulation.

Information levels are currently a deterministic **interpolation proxy**:
`perceived_cost = (1-alpha)*free_flow_cost + alpha*current_cost`.
This is an explicit modelling assumption, not a Bayesian/noisy information model.
All agents use selfish shortest-path routing.

`results.json` includes completion status, timestep count and per-agent costs.
With `record_history=true`, `history.json` stores snapshots for playback.
`max_steps_reached` means incomplete, not an equilibrium.

The runner does not yet implement batch sweeps, file-upload UI, travel-time edge
occupancy, or equilibrium/optimal-flow baselines. Use separate scenario folders
for different input cases until batch automation is added.
