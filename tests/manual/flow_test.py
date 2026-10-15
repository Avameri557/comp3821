from src.networks.network import Network

network = Network()

network.add_edge(1, 2, a=2, b=1)
network.add_edge(2, 4, a=2, b=1)

network.add_edge(1, 3, a=3, b=0.2)
network.add_edge(3, 4, a=3, b=0.2)

# Test 1: No congestion
path = network.shortest_path(1, 4)

print("Initial shortest path:", path)
print("Initial path cost:", network.path_cost(path))

# Test 2: Add congestion
network.get_edge(1, 2).flow = 5
network.get_edge(2, 4).flow = 5

path = network.shortest_path(1, 4)

print("New shortest path:", path)
print("New path cost:", network.path_cost(path))
print("Total network cost:", network.total_cost())