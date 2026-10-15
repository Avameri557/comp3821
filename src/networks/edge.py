from dataclasses import dataclass

@dataclass
class Edge:
    source: int
    target: int
    a: float
    b: float
    flow: float = 0.0

    def cost(self, flow=None):
        if flow is None:
            flow = self.flow
        # Congestion Cost function, a -> base cost, b -> flow sensitivity, f -> current flow
        return self.a + self.b * flow
        
