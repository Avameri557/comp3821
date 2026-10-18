import networkx as nx
from components.agent import Agent, InformationModel
from components.routing_strategies import SelfishRouting

# Small test network
network = nx.DiGraph()
network.add_edge(1, 2, cost=2)
network.add_edge(1, 3, cost=5)
network.add_edge(2, 4, cost=3)
network.add_edge(3, 4, cost=1)

agent = Agent(
    agent_id=0,
    origin=1,
    destination=4
)

information = InformationModel(alpha=agent.alpha)
strategy = SelfishRouting()

while not agent.arrived:
    perceived_costs = information.get_perceived_costs(network)

    next_node = strategy.choose_next_node(
        agent, network, perceived_costs
    )

    if next_node is None:
        break

    actual_cost = network[agent.current_node][next_node]["cost"]
    agent.move(next_node, actual_cost)

print(agent.route_history)
print(agent.total_cost)
