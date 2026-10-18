import argparse
import json
from pathlib import Path

from src.simulation.scenario_loader import load_scenario


def serializable_snapshot(snapshot):
    """JSON does not support tuple-key dictionaries."""
    result = dict(snapshot)
    for key in ("previous_flows", "new_flows"):
        result[key] = [
            {"source": u, "target": v, "flow": flow}
            for (u, v), flow in snapshot[key].items()
        ]
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    simulation, config = load_scenario(args.scenario)
    result = simulation.run_until_complete(config.get("max_timesteps", 10000))
    output_dir = args.output or Path(config.get("output_directory", "results"))
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    if simulation.record_history:
        history = [serializable_snapshot(step) for step in simulation.history]
        (output_dir / "history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "agents"}, indent=2))


if __name__ == "__main__":
    main()