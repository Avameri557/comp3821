import unittest

from src.components.agent import Agent, InformationModel
from src.components.network import Network
from src.simulation.simulator import Simulation
from src.simulation.runner import serializable_snapshot


def two_routes():
    network = Network()
    network.add_edge(1, 2, a=1, b=2)
    network.add_edge(2, 4, a=1, b=0)
    network.add_edge(1, 3, a=3, b=0)
    network.add_edge(3, 4, a=1, b=0)
    return network


class PredictiveReassessmentTests(unittest.TestCase):
    def test_alpha_zero_sees_no_intentions(self):
        network = two_routes()
        agents = [Agent(i, 1, 4, alpha=0) for i in range(3)]
        sim = Simulation(network, agents, seed=7)
        snapshot = sim.step()
        self.assertEqual(snapshot["initial_flows"][(1, 2)], 3)
        self.assertEqual(snapshot["new_flows"][(1, 2)], 3)
        self.assertFalse(any(d["reassessed"] for d in snapshot["decisions"]))

    def test_alpha_one_observes_all_other_initial_choices(self):
        network = two_routes()
        agents = [Agent(i, 1, 4, alpha=1) for i in range(3)]
        sim = Simulation(network, agents, seed=7)
        snapshot = sim.step()
        self.assertEqual(snapshot["initial_flows"][(1, 2)], 3)
        self.assertEqual(snapshot["new_flows"][(1, 3)], 3)
        self.assertTrue(all(d["reassessed"] for d in snapshot["decisions"]))
        # Actual costs use final choices, not the provisional flow.
        self.assertTrue(all(d["actual_cost"] == 3 for d in snapshot["decisions"]))

    def test_seed_is_reproducible(self):
        def trial():
            sim = Simulation(
                two_routes(), [Agent(i, 1, 4, alpha=0.5) for i in range(12)],
                seed=123,
            )
            return sim.step()["decisions"]
        self.assertEqual(trial(), trial())

    def test_history_is_json_serializable(self):
        sim = Simulation(two_routes(), [Agent(0, 1, 4, alpha=1)], seed=1)
        import json
        json.dumps(serializable_snapshot(sim.step()))

    def test_run_completes(self):
        sim = Simulation(two_routes(), [Agent(i, 1, 4, alpha=1) for i in range(4)])
        result = sim.run_until_complete(max_steps=5)
        self.assertTrue(result["completed"])
        self.assertEqual(result["arrived_count"], 4)

    def test_sampling_excludes_self(self):
        network = two_routes()
        agent = Agent(0, 1, 4, alpha=1)
        other = Agent(1, 1, 4, alpha=1)
        intentions = [
            {"agent": agent, "source": 1, "target": 2},
            {"agent": other, "source": 1, "target": 2},
        ]
        costs = InformationModel(1).get_perceived_costs(
            network, intentions, agent=agent
        )
        self.assertEqual(costs[(1, 2)], 3)


if __name__ == "__main__":
    unittest.main()
