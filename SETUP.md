## Running the project

Run the following from the repository root. Install dependencies using either `pip` or Conda:

```sh
python -m pip install -r requirements.txt
# Or: conda env create -f environment.yaml && conda activate comp3821
```

**Run experiments:**

```sh
python -m src.experiments                                                # three core experiments, all networks
python -m src.experiments --network pigou --test symmetric               # one experiment on one network
python -m src.experiments --test informed_rising                          # optional α=0 comparison
python -m src.experiments --step 0.01 --trials 500 --output results_fine  # fine sweeps
python -m src.experiments --cap                                           # capped-estimate sweeps
python -m src.experiments --cap --step 0.01 --trials 500 --output results_capped_fine
python -m src.experiments --plot-only --output results_fine               # redraw fine plots from CSVs
```

By default the runner uses **200 trials** and α increments of **0.05**. `--network` and `--test` can be repeated, `--workers` controls parallel processes, and `--output` selects the results directory. Running experiments into an existing directory will overwrite the corresponding CSVs and plots; use a separate `--output` directory if you want to preserve the committed datasets.

**Compute benchmarks:**

```sh
python -m src.benchmarks.frank_wolfe --scenario scenarios/sioux_falls --show-paths
```

**Regenerate network images** (requires `pdflatex` and `pdftoppm`):

```sh
./diagrams/build.sh
```

Simulation options live in each [`scenarios/`](scenarios/) directory's `config.json`. The standard configurations use `revision_percentage: 100` and `forward_only: true`; optional estimate capping can be selected with `--cap`.

## Contributing

Work on a **separate branch** rather than committing directly to `main`, ideally named `category/feature` (for example, `docs/readme-navigation` or `simulation/automation`). Keep commits focused on one logical change and clearly describe what changed.

Use commit messages in the format **`category: short description`**, for example:

```text
feat: implemented automatic generation
fix: correct congestion calculation
refactor: simplify experiment selection
docs: update simulation procedure
chore: archive historical analysis
```

Prefer `feat` for functionality, `fix` for bug fixes, `refactor` for restructuring without changed behaviour, `docs` for documentation, and `chore` for maintenance. Review changes and run the relevant experiment or check before opening a pull request into `main`.