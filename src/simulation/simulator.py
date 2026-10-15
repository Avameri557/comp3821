from collections import Counter

from src.agents.agent import Agent, InformationModel
from src.networks.network import Network
from src.agents.routing_strategies import SelfishRouting


class Simulation:
    def __init__(self, network, agents):
        self.network = network
        self.agents = agents
        self.routing = SelfishRouting()

        self.timestep = 0
        self.history = []

    def step(self):
        # 1. Record the previous network state
        previous_flows = {
            (u, v): data["edge"].flow
            for u, v, data in self.network.graph.edges(data=True)
        }

        # 2. All agents make decisions before anyone moves
        decisions = []

        for agent in self.agents:
            if agent.arrived:
                continue

            information = InformationModel(agent.alpha)

            perceived_costs = information.get_perceived_costs(
                self.network
            )

            next_node = self.routing.choose_next_node(
                agent,
                self.network.graph,
                perceived_costs
            )

            if next_node is not None:
                decisions.append({
                    "agent": agent,
                    "source": agent.current_node,
                    "target": next_node,
                    "perceived_cost": perceived_costs[
                        (agent.current_node, next_node)
                    ]
                })

        # 3. Count the agents selecting each edge
        new_flows = Counter(
            (d["source"], d["target"])
            for d in decisions
        )

        # 4. Update edge congestion simultaneously
        for u, v, data in self.network.graph.edges(data=True):
            data["edge"].flow = new_flows[(u, v)]

        # 5. Move agents and charge actual congestion costs
        decision_log = []

        for decision in decisions:
            agent = decision["agent"]
            source = decision["source"]
            target = decision["target"]

            actual_cost = self.network.get_edge(
                source, target
            ).cost()

            agent.move(target, actual_cost)

            decision_log.append({
                "agent_id": agent.agent_id,
                "source": source,
                "target": target,
                "perceived_cost": decision["perceived_cost"],
                "actual_cost": actual_cost
            })

        # 6. Record the completed timestep
        snapshot = {
            "timestep": self.timestep,
            "previous_flows": previous_flows,
            "decisions": decision_log,
            "new_flows": dict(new_flows),
            "positions": {
                agent.agent_id: agent.current_node
                for agent in self.agents
            },
            "total_cost": sum(
                agent.total_cost for agent in self.agents
            )
        }

        self.history.append(snapshot)
        self.timestep += 1

        return snapshot

    def run(self, max_steps=100):
        for _ in range(max_steps):
            if all(agent.arrived for agent in self.agents):
                break

            yield self.step()


def display_step(snapshot):
    print(f"\n--- Timestep {snapshot['timestep']} ---")

    print("Previous congestion:")
    print(snapshot["previous_flows"])

    print("\nAgent decisions:")
    for d in snapshot["decisions"]:
        print(
            f"Agent {d['agent_id']}: "
            f"{d['source']} -> {d['target']} | "
            f"Perceived: {d['perceived_cost']:.2f} | "
            f"Actual: {d['actual_cost']:.2f}"
        )

    print("\nUpdated congestion:")
    print(snapshot["new_flows"])

    print("Agent positions:")
    print(snapshot["positions"])

    print(f"Accumulated cost: {snapshot['total_cost']:.2f}")


if __name__ == "__main__":
    network = Network()

    network.add_edge(1, 2, a=2, b=1)
    network.add_edge(2, 4, a=2, b=1)
    network.add_edge(1, 3, a=3, b=0.2)
    network.add_edge(3, 4, a=3, b=0.2)

    agents = [
        Agent(agent_id=i, origin=1, destination=4)
        for i in range(5)
    ]

    simulation = Simulation(network, agents)

    for snapshot in simulation.run():
        display_step(snapshot)

    print("\n--- Final Results ---")
    for agent in agents:
        print(
            f"Agent {agent.agent_id}: "
            f"Route {agent.route_history}, "
            f"Cost {agent.total_cost:.2f}"
        )
