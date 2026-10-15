from src.agents.agent import Agent
from src.networks.network import Network
from src.simulation.simulator import Simulation, display_step


def create_network():
    """Create the four-node network used in our experiment."""
    network = Network()

    network.add_edge(1, 2, a=2, b=1)
    network.add_edge(2, 4, a=2, b=1)
    network.add_edge(1, 3, a=3, b=0.2)
    network.add_edge(3, 4, a=3, b=0.2)

    return network


def create_simulation(num_agents=5):
    network = create_network()

    agents = [
        Agent(agent_id=i, origin=1, destination=4, alpha=1.0)
        for i in range(num_agents)
    ]

    return Simulation(network, agents)


def test_initial_state():
    """Check that agents and edge flows start correctly."""
    sim = create_simulation()

    assert sim.timestep == 0
    assert len(sim.agents) == 5

    for agent in sim.agents:
        assert agent.current_node == 1
        assert agent.route_history == [1]
        assert agent.total_cost == 0
        assert not agent.arrived

    for _, _, data in sim.network.graph.edges(data=True):
        assert data["edge"].flow == 0

    print("PASS: Initial state")


def test_first_step():
    """All five agents should select edge 1 -> 2."""
    sim = create_simulation()
    snapshot = sim.step()

    display_step(snapshot)

    # Every agent observes the original, uncongested network
    assert all(
        flow == 0
        for flow in snapshot["previous_flows"].values()
    )

    # All five agents choose the same selfish route
    assert len(snapshot["decisions"]) == 5

    for decision in snapshot["decisions"]:
        assert decision["source"] == 1
        assert decision["target"] == 2
        assert decision["perceived_cost"] == 2
        assert decision["actual_cost"] == 7

    # Congestion is updated after all decisions
    assert sim.network.get_edge(1, 2).flow == 5
    assert sim.network.get_edge(1, 3).flow == 0
    assert sim.network.get_edge(2, 4).flow == 0
    assert sim.network.get_edge(3, 4).flow == 0

    for agent in sim.agents:
        assert agent.current_node == 2
        assert agent.route_history == [1, 2]
        assert agent.total_cost == 7
        assert not agent.arrived

    assert sim.timestep == 1
    assert len(sim.history) == 1

    print("PASS: First timestep")


def test_second_step():
    """All five agents should move from node 2 to node 4."""
    sim = create_simulation()

    sim.step()
    snapshot = sim.step()

    display_step(snapshot)

    # The previous timestep's congestion is observed
    assert snapshot["previous_flows"][(1, 2)] == 5
    assert snapshot["previous_flows"][(2, 4)] == 0

    for decision in snapshot["decisions"]:
        assert decision["source"] == 2
        assert decision["target"] == 4
        assert decision["perceived_cost"] == 2
        assert decision["actual_cost"] == 7

    # Previous edge flow is cleared
    assert sim.network.get_edge(1, 2).flow == 0
    assert sim.network.get_edge(2, 4).flow == 5

    for agent in sim.agents:
        assert agent.current_node == 4
        assert agent.arrived
        assert agent.route_history == [1, 2, 4]
        assert agent.total_cost == 14

    assert snapshot["total_cost"] == 70
    assert sim.timestep == 2
    assert len(sim.history) == 2

    print("PASS: Second timestep")


def test_simultaneous_decisions():
    """
    Check that agents do not observe other agents'
    decisions within the same timestep.
    """
    sim = create_simulation(num_agents=10)

    snapshot = sim.step()

    # Despite congestion increasing to 10,
    # every agent should perceive the initial cost of 2.
    assert len(snapshot["decisions"]) == 10

    for decision in snapshot["decisions"]:
        assert decision["target"] == 2
        assert decision["perceived_cost"] == 2
        assert decision["actual_cost"] == 12

    assert sim.network.get_edge(1, 2).flow == 10

    print("PASS: Simultaneous decision-making")


def test_previous_congestion_affects_routing():
    """
    Set congestion on route A before agents decide.
    Agents should then prefer route B.
    """
    sim = create_simulation()

    # Simulate congestion from a previous timestep
    sim.network.get_edge(1, 2).flow = 5
    sim.network.get_edge(2, 4).flow = 5

    # Route A: (2+5) + (2+5) = 14
    # Route B: 3 + 3 = 6
    snapshot = sim.step()

    for decision in snapshot["decisions"]:
        assert decision["source"] == 1
        assert decision["target"] == 3
        assert decision["perceived_cost"] == 3
        assert decision["actual_cost"] == 4

    assert sim.network.get_edge(1, 2).flow == 0
    assert sim.network.get_edge(1, 3).flow == 5

    print("PASS: Congestion changes route selection")


def test_completed_agents_do_not_move():
    """Agents that reach their destination should stay there."""
    sim = create_simulation()

    snapshots = list(sim.run(max_steps=10))

    assert len(snapshots) == 2
    assert all(agent.arrived for agent in sim.agents)

    previous_positions = [
        agent.current_node for agent in sim.agents
    ]

    # Running again should not produce further timesteps
    assert list(sim.run(max_steps=10)) == []

    assert [
        agent.current_node for agent in sim.agents
    ] == previous_positions

    print("PASS: Completed agents remain at destination")


def run_all_tests():
    tests = [
        test_initial_state,
        test_first_step,
        test_second_step,
        test_simultaneous_decisions,
        test_previous_congestion_affects_routing,
        test_completed_agents_do_not_move
    ]

    print("=== ROUTING SIMULATION TESTS ===")

    for test in tests:
        test()

    print("\nAll tests passed!")


if __name__ == "__main__":
    run_all_tests()
