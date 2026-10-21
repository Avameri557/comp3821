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