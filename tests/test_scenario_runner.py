import json

from src.simulation.scenarios import load_scenario


def test_example_scenario_completes():
    sim, config = load_scenario("scenarios/example")
    result = sim.run_until_complete(config["max_timesteps"])
    assert result["completed"]
    assert result["arrived_count"] == 3
    assert result["timesteps"] == 2
    assert len(sim.history) == 2


def test_partial_information_interpolates():
    from src.agents.agent import InformationModel
    from src.networks.network import Network
    net = Network()
    net.add_edge(1, 2, a=2, b=3)
    net.get_edge(1, 2).flow = 4
    assert InformationModel(0).get_perceived_costs(net)[(1, 2)] == 2
    assert InformationModel(0.5).get_perceived_costs(net)[(1, 2)] == 8
    assert InformationModel(1).get_perceived_costs(net)[(1, 2)] == 14


def test_initially_arrived():
    from src.agents.agent import Agent
    from src.networks.network import Network
    from src.simulation.simulator import Simulation
    net = Network()
    net.graph.add_node(1)
    sim = Simulation(net, [Agent(0, 1, 1)])
    assert sim.run_until_complete()["completed"]
    assert sim.timestep == 0
