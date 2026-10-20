# Automatic agent generation

Use the `generate` object in `agents.json` instead of manually listing agents:

```json
{
  "generate": {
    "count": 30,
    "sources": [1, 2, 3],
    "destinations": [4],
    "alpha": 0.5
  }
}
```

- `count`: number of agents to create (nonnegative integer).
- `sources`: nonempty list of candidate starting nodes.
- `destinations`: nonempty list of candidate ending nodes.
- `alpha`: shared predictive-information parameter in [0, 1].

The loader uniformly samples from all **reachable, distinct**
(source, destination) pairs. This excludes invalid or same-node trips.
It assigns sequential IDs `0, 1, ..., count - 1`.

For reproducibility, set `"seed": 42` in `config.json`.
The same seed produces the same agent assignments. The simulator uses
a separate random-number generator for predictive observations.

Run the provided scenario from the repository root:

```bash
python -m src.simulation.runner --scenario scenarios/generated --output results/generated
python -m unittest discover -s tests -p 'test_*.py'
```

The previous explicit `"agents": [...]` format still works, so old
scenarios do not need to change. Specify **either** `generate` or `agents`,
not both.

This implementation supports one fixed `alpha` for all generated
agents. Sampling `alpha` from a distribution is reserved for a future
extension.
