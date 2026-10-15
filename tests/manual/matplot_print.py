import networkx as nx
import matplotlib.pyplot as plt

# Create a directed graph
G = nx.DiGraph()

# Add directed edges with travel costs
G.add_weighted_edges_from([
    ("A", "B", 3),
    ("A", "C", 5),
    ("B", "C", 2),
    ("B", "D", 4),
    ("C", "D", 1)
])

# Print graph information
print("Nodes:", list(G.nodes))
print("Edges:", list(G.edges(data=True)))

# Specify node positions for plotting
pos = {
    "A": (0, 1),
    "B": (1, 2),
    "C": (1, 0),
    "D": (2, 1)
}

# Draw nodes and directed edges
nx.draw(
    G,
    pos,
    with_labels=True,
    node_color="lightblue",
    node_size=1500,
    arrows=True,
    arrowsize=20,
    font_size=12
)

# Display edge weights
edge_labels = nx.get_edge_attributes(G, "weight")
nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels)

plt.title("Simple Routing Network")
plt.show()