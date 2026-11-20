# Historical social-optimum derivations

This directory archives analytical work from an earlier version of the COMP3821 routing simulator.

The documents here study **per-timestep congestion**, charging each edge for the agents crossing it together in a timestep. The current `src/simulation/simulator.py` instead charges for **whole-run edge flow**, so the historical dynamic optima and some experimental values are **not** the benchmarks for the current poster/report.

For the current experimental model, use `src/benchmarks/frank_wolfe.py`, the scenario definitions in `scenarios/`, and the CSVs in `results/`. The historical PDFs and TeX sources are preserved for reference, not included in the default experimental workflow. TeX diagram paths have been updated for the archive location; older references to experimental datasets may no longer resolve.
