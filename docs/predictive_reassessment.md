# Predictive reassessment (experimental branch)

This branch keeps the existing discrete-timestep network, routing strategy,
scenario format, and linear congestion cost `c_e(f) = a_e + b_e f`.

## Decision protocol

1. Every active agent independently chooses a provisional next edge using
   free-flow shortest paths. All provisional choices are frozen.
2. Each agent samples each *other* active agent's provisional choice with
   independent probability `alpha`. For an edge with `k` observed
   intentions, the estimated number of other intending agents is
   `k / alpha` when `alpha > 0`; for `alpha = 0`, the estimate is zero.
3. The agent evaluates each possible outgoing first edge with its own
   prospective entry added to the estimated flow and selects its final
   shortest path. Downstream edges use the estimated intention costs
   without a fictitious extra entry.
4. All final first-edge choices are committed simultaneously. The existing
   simulator's edge-cost and movement semantics remain unchanged.

**Interpretation:** `alpha=1` means all *initial intentions* are visible,
not that final choices are known. Reassessment is simultaneous, so
high-information agents can overreact together. `alpha=0` has no knowledge
of other agents' intentions. Initial choices currently use free-flow costs
for all agents; prior-step edge occupancy is retained in history but is not
part of prediction. This is intentional for a simultaneous-entry experiment.

## Reproducibility

Set `"seed": 123` in a scenario's `config.json` to reproduce random
sampling. `agents.json` still uses `alpha` in [0,1]. When history is
enabled, each step records `initial_flows`, `new_flows`, and per-agent
`initial_target` and `reassessed` fields.

Run an existing scenario with:

```bash
python -m src.simulation.runner --scenario scenarios/example --output results/predictive
python -m unittest discover -s tests -p 'test_*.py'
```

## Limitations

The existing simulation moves agents across an edge in one timestep while
charging a congestion-dependent cost; it is not a physical queueing model.
Intention estimates apply to the next edge, not a full future path.
These experiments should not be treated as Wardrop equilibrium calculations.
Random sampling can cause high variance for small nonzero alpha.
