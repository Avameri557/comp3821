import json
import tempfile
import unittest
from pathlib import Path

from src.components.network import Network
from src.simulation.scenario_loader import generate_agents, load_scenario
import random


def network():
    n = Network()
    n.add_edge(1, 2, a=1, b=1)
    n.add_edge(2, 4, a=1, b=1)
    n.add_edge(1, 3, a=1, b=1)
    n.add_edge(3, 4, a=1, b=1)
    return n


class AgentGenerationTests(unittest.TestCase):
    def test_count_ids_alpha_and_valid_pairs(self):
        spec = {"count": 100, "sources": [1, 2, 3], "destinations": [1, 4], "alpha": 0.6}
        agents = generate_agents(spec, network(), random.Random(12))
        self.assertEqual([a.agent_id for a in agents], list(range(100)))
        self.assertTrue(all(a.alpha == 0.6 for a in agents))
        self.assertTrue(all(a.origin != a.destination for a in agents))
        self.assertTrue(all(a.destination == 4 for a in agents))
        self.assertTrue(all(a.origin in (1, 2, 3) for a in agents))

    def test_seed_reproducibility(self):
        spec = {"count": 50, "sources": [1, 2, 3], "destinations": [4], "alpha": 0.5}
        def pairs():
            return [(a.origin, a.destination) for a in generate_agents(spec, network(), random.Random(42))]
        self.assertEqual(pairs(), pairs())

    def test_rejects_invalid_parameters(self):
        base = {"count": 2, "sources": [1], "destinations": [4], "alpha": 0.5}
        for override in ({"count": -1}, {"count": True}, {"alpha": 1.1},
                         {"alpha": None}, {"sources": []}, {"destinations": [9]},
                         {"sources": [1, 1]}, {"destinations": [1]}):
            with self.subTest(override=override):
                with self.assertRaises(ValueError):
                    generate_agents({**base, **override}, network(), random.Random(1))

    def test_zero_count(self):
        spec = {"count": 0, "sources": [1], "destinations": [4], "alpha": 0}
        self.assertEqual(generate_agents(spec, network(), random.Random(1)), [])

    def test_loader_accepts_generated_and_legacy_modes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "network.json").write_text(json.dumps({
                "nodes": [1, 2, 4],
                "edges": [{"from": 1, "to": 2, "a": 1, "b": 1},
                          {"from": 2, "to": 4, "a": 1, "b": 1}]
            }))
            (root / "config.json").write_text('{"seed": 7}')
            (root / "agents.json").write_text(json.dumps({
                "generate": {"count": 10, "sources": [1], "destinations": [4], "alpha": 0.2}
            }))
            sim, _ = load_scenario(root)
            self.assertEqual(len(sim.agents), 10)
            (root / "agents.json").write_text(json.dumps({
                "agents": [{"id": 23, "origin": 1, "destination": 4, "alpha": 0.7}]
            }))
            sim, _ = load_scenario(root)
            self.assertEqual(sim.agents[0].agent_id, 23)


if __name__ == "__main__":
    unittest.main()
