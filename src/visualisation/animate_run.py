"""
Animate a simulation run: vertices, edges shaded by traffic, and groups of
agents moving along the edges, coloured by information level (alpha).

Several information mixes can be shown side by side on the same scenario and
seed, which is the easiest way to see what information changes.

Usage:
    # one panel, alphas as in agents.json
    python -m src.visualisation.animate_run --scenario scenarios/braess

    # side by side: no information, half, full
    python -m src.visualisation.animate_run --scenario scenarios/braess \
        --population 0 --population 0.5 --population 1

    # mixed population: 10% fully informed, 90% blind
    python -m src.visualisation.animate_run --scenario scenarios/braess \
        --population 1:0.1,0

    # save a GIF (or .mp4 if ffmpeg is installed) instead of opening a window
    python -m src.visualisation.animate_run --scenario scenarios/sioux_falls \
        --population 0 --population 1 --save results/sioux_falls_demo.gif --no-show

    # save a still image of step 2
    python -m src.visualisation.animate_run --scenario scenarios/pigou \
        --snapshot 0.5 results/pigou_step.png --no-show

Window controls: Play/Pause button or space bar, left/right arrows to step,
drag the slider to scrub through time.
"""

import argparse
import json
import math
from collections import defaultdict, deque
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from matplotlib.collections import LineCollection

from src.visualisation.populations import describe_population, make_simulation, parse_population


# --------------------------------------------------------------------------- layout

def node_positions(scenario, graph, origins):
    """Real coordinates if network.json has them, else layers by hop distance from the origins."""
    network_data = json.loads((Path(scenario) / "network.json").read_text(encoding="utf-8"))
    coords = network_data.get("coordinates")
    if coords:
        return {int(node): (float(x), float(y)) for node, (x, y) in coords.items()}

    depth = {o: 0 for o in origins}
    queue = deque(origins)
    while queue:
        u = queue.popleft()
        for v in graph.successors(u):
            if v not in depth:
                depth[v] = depth[u] + 1
                queue.append(v)
    deepest = max(depth.values(), default=0)
    layered = nx.DiGraph()
    for node in sorted(graph.nodes):
        layered.add_node(node, layer=depth.get(node, deepest + 1))
    pos = nx.multipartite_layout(layered, subset_key="layer")
    # multipartite_layout lists each layer bottom-to-top; flip so low ids are on top.
    return {node: (float(x), -float(y)) for node, (x, y) in pos.items()}


def edge_geometry(graph, pos):
    """Start/end points per directed edge, shifted sideways when both directions exist."""
    lengths = [math.dist(pos[u], pos[v]) for u, v in graph.edges]
    offset = 0.06 * (np.median(lengths) if lengths else 1.0)
    geometry = {}
    for u, v in graph.edges:
        (x0, y0), (x1, y1) = pos[u], pos[v]
        if graph.has_edge(v, u):
            dx, dy = x1 - x0, y1 - y0
            norm = math.hypot(dx, dy) or 1.0
            # shift to the right of the direction of travel (keep-right)
            nx_, ny_ = dy / norm * offset, -dx / norm * offset
            x0, y0, x1, y1 = x0 + nx_, y0 + ny_, x1 + nx_, y1 + ny_
        geometry[(u, v)] = ((x0, y0), (x1, y1))
    return geometry, offset


def point_on(geometry, edge, s):
    (x0, y0), (x1, y1) = geometry[edge]
    return x0 + (x1 - x0) * s, y0 + (y1 - y0) * s


def cost_label(edge):
    if edge.kind == "bpr":
        return f"t0={edge.a:g}"
    if edge.b == 0:
        return f"{edge.a:g}"
    if edge.a == 0:
        return f"{edge.b:g}f"
    return f"{edge.a:g}+{edge.b:g}f"


# --------------------------------------------------------------------------- one panel

class Panel:
    def __init__(self, scenario, groups, seed, max_steps):
        self.simulation, config = make_simulation(scenario, groups, seed, record_history=True)
        self.label = describe_population(groups, self.simulation.agents)
        steps = max_steps if max_steps is not None else config.get("max_timesteps", 10000)
        self.result = self.simulation.run_until_complete(steps)
        self.steps = self.simulation.timestep
        self.history = self.simulation.history
        self.agents = self.simulation.agents
        self.routes = [agent.route_history for agent in self.agents]
        self.n = len(self.agents)
        self.heats = len({agent.heat for agent in self.agents})

    def max_flow(self):
        return max((f for snap in self.history for f in snap["new_flows"].values()), default=1)

    def final_costs_by_alpha(self):
        totals = defaultdict(list)
        for agent in self.agents:
            totals[agent.alpha].append(agent.total_cost)
        return {a: sum(c) / len(c) for a, c in sorted(totals.items(), reverse=True)}

    def groups_at(self, t):
        """{(kind, place, alpha): count} for agents travelling at time t, plus
        arrivals per destination and agents not yet released per origin."""
        groups = defaultdict(int)
        arrived = defaultdict(int)
        waiting = defaultdict(int)
        s = 0.0
        for agent, route in zip(self.agents, self.routes):
            if t < agent.release_time - 1e-9:
                waiting[agent.origin] += 1
                continue
            local = t - agent.release_time   # time since this agent was released
            k = int(math.floor(local + 1e-9))
            s = local - k
            last = len(route) - 1
            if local >= last - 1e-9 and agent.arrived:
                arrived[route[-1]] += 1
            elif k >= last:  # never arrived and ran out of steps: stays where it is
                groups[("node", route[-1], agent.alpha)] += 1
            elif s < 1e-9:
                groups[("node", route[k], agent.alpha)] += 1
            else:
                groups[("edge", (route[k], route[k + 1]), agent.alpha)] += 1
        frac = t - math.floor(t + 1e-9)  # release times are whole steps, so all agents share it
        return groups, arrived, waiting, frac

    def cumulative_cost(self, t):
        k = min(int(math.floor(t + 1e-9)), self.steps)
        return self.history[k - 1]["total_cost"] if k > 0 else 0.0


# --------------------------------------------------------------------------- figure

class Viewer:
    def __init__(self, scenario, panels, fps_per_step=10):
        self.scenario = Path(scenario)
        self.panels = panels
        self.graph = panels[0].simulation.network.graph
        self.network = panels[0].simulation.network
        origins = sorted({a.origin for p in panels for a in p.agents})
        self.origins = set(origins)
        self.destinations = {a.destination for p in panels for a in p.agents}
        self.pos = node_positions(scenario, self.graph, origins)
        self.geometry, self.offset = edge_geometry(self.graph, self.pos)
        self.total_steps = max(p.steps for p in panels)
        self.fps_per_step = fps_per_step
        self.max_flow = max(p.max_flow() for p in panels) or 1
        # marker sizes are relative to one heat (all agents when there are no heats)
        self.max_agents = max(p.n / p.heats for p in panels) or 1
        self.small = self.graph.number_of_edges() <= 16

        alphas = sorted({a.alpha for p in panels for a in p.agents}, reverse=True)
        cmap = matplotlib.colormaps["viridis"]
        self.colour = {a: cmap(0.85 * a) for a in alphas} if len(alphas) > 1 else {alphas[0]: cmap(0.55)}

        n = len(panels)
        self.fig = plt.figure(figsize=(max(8.0, 5.6 * n), 6.8))
        self.axes = [self.fig.add_axes([i / n + 0.01, 0.17, 1 / n - 0.02, 0.73]) for i in range(n)]
        heats = panels[0].heats
        per_heat = f" ({heats} heats of {panels[0].n // heats})" if heats > 1 else ""
        self.fig.suptitle(f"{self.scenario.name}: {panels[0].n} agents{per_heat}", fontsize=13)
        self.dynamic = [dict() for _ in panels]
        for ax, panel, store in zip(self.axes, panels, self.dynamic):
            self._draw_static(ax, panel, store)
        self._legend()
        self.time = 0.0
        self.playing = False
        self.slider = None

    # ---------------------------------------------------------------- static parts
    def _draw_static(self, ax, panel, store):
        xs = [p[0] for p in self.pos.values()]
        ys = [p[1] for p in self.pos.values()]
        pad_x = (max(xs) - min(xs)) * 0.08 + 0.05 * (max(ys) - min(ys) + 1e-9)
        pad_y = (max(ys) - min(ys)) * 0.08 + 0.05 * (max(xs) - min(xs) + 1e-9)
        ax.set_xlim(min(xs) - pad_x, max(xs) + pad_x)
        ax.set_ylim(min(ys) - pad_y, max(ys) + pad_y)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_title(panel.label, fontsize=11)

        for edge, ((x0, y0), (x1, y1)) in self.geometry.items():
            ax.plot([x0, x1], [y0, y1], color="#c8c8c8", lw=1.0, zorder=1, solid_capstyle="round")
            ax.annotate(
                "", xy=point_on(self.geometry, edge, 0.62), xytext=point_on(self.geometry, edge, 0.52),
                arrowprops=dict(arrowstyle="-|>", color="#a0a0a0", lw=1.0, mutation_scale=9), zorder=1,
            )
            if self.small:
                # label beside the edge midpoint, on the side away from the centre of the graph
                (x0, y0), (x1, y1) = self.geometry[edge]
                norm = math.hypot(x1 - x0, y1 - y0) or 1.0
                mx, my = point_on(self.geometry, edge, 0.5)
                px, py = -(y1 - y0) / norm, (x1 - x0) / norm
                cx = sum(p[0] for p in self.pos.values()) / len(self.pos)
                cy = sum(p[1] for p in self.pos.values()) / len(self.pos)
                if (mx - cx) * px + (my - cy) * py < 0:
                    px, py = -px, -py
                lx, ly = mx + px * self.offset * 2.6, my + py * self.offset * 2.6
                ax.text(lx, ly, cost_label(self.network.get_edge(*edge)), fontsize=8, color="#666666",
                        ha="center", va="center", zorder=2,
                        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8))

        flow_lines = LineCollection([], zorder=2, capstyle="round")
        ax.add_collection(flow_lines)
        store["flows"] = flow_lines

        node_size = 420 if self.small else 170
        for node, (x, y) in self.pos.items():
            edge_colour = "#2e7d32" if node in self.origins else "#b71c1c" if node in self.destinations else "#333333"
            width = 2.2 if (node in self.origins or node in self.destinations) else 1.0
            ax.scatter([x], [y], s=node_size, facecolor="white", edgecolor=edge_colour, linewidth=width, zorder=3)
            ax.text(x, y, str(node), fontsize=8 if self.small else 6.5, ha="center", va="center", zorder=4)

        store["agents"] = ax.scatter([], [], zorder=5, edgecolor="white", linewidth=0.6)
        store["labels"] = []
        store["status"] = ax.text(0.01, -0.02, "", transform=ax.transAxes, fontsize=9, va="top", family="monospace")
        finals = panel.final_costs_by_alpha()
        summary = "final avg cost  " + "   ".join(f"α={a:g}: {c:.2f}" for a, c in finals.items())
        if not panel.result["completed"]:
            stuck = panel.n - panel.result["arrived_count"]
            summary += f"\n{stuck} agents never arrived (max steps reached)"
        ax.text(0.01, -0.085, summary, transform=ax.transAxes, fontsize=9, va="top", family="monospace")

    def _legend(self):
        handles = [
            plt.Line2D([], [], marker="o", ls="", markersize=9, markerfacecolor=c, markeredgecolor="white",
                       label=f"agents α={a:g}")
            for a, c in self.colour.items()
        ]
        handles += [
            plt.Line2D([], [], marker="o", ls="", markersize=8, markerfacecolor="white",
                       markeredgecolor="#2e7d32", markeredgewidth=2, label="origin"),
            plt.Line2D([], [], marker="o", ls="", markersize=8, markerfacecolor="white",
                       markeredgecolor="#b71c1c", markeredgewidth=2, label="destination"),
            plt.Line2D([], [], color=matplotlib.colormaps["Reds"](0.75), lw=4, label="edge traffic this step"),
        ]
        ncol = len(handles) if len(self.panels) > 1 else min(len(handles), 4)
        self.fig.legend(handles=handles, loc="lower center", ncol=ncol, fontsize=9,
                        frameon=False, bbox_to_anchor=(0.5, 0.005))

    # ---------------------------------------------------------------- dynamic parts
    def draw(self, t):
        self.time = t
        k = int(math.floor(t + 1e-9))
        reds = matplotlib.colormaps["Reds"]
        span = self.offset * 1.4
        for ax, panel, store in zip(self.axes, self.panels, self.dynamic):
            # groups with different alphas at the same spot are spread around it
            panel_alphas = sorted({a.alpha for a in panel.agents}, reverse=True)
            alpha_index = {a: i for i, a in enumerate(panel_alphas)}
            # traffic on edges during the move from step k to k+1
            flows = panel.history[k]["new_flows"] if k < panel.steps else {}
            segments, widths, colours = [], [], []
            for edge, f in flows.items():
                if f <= 0:
                    continue
                segments.append(self.geometry[edge])
                share = f / self.max_flow
                widths.append(1.5 + 9 * share)
                colours.append(reds(0.3 + 0.65 * share))
            store["flows"].set_segments(segments)
            store["flows"].set_linewidths(widths)
            store["flows"].set_colors(colours)

            # agent groups
            groups, arrived, waiting, s = panel.groups_at(min(t, panel.steps))
            points, sizes, colors = [], [], []
            for label in store["labels"]:
                label.remove()
            store["labels"] = []
            for (kind, place, alpha), count in groups.items():
                if kind == "node":
                    x, y = self.pos[place]
                else:
                    x, y = point_on(self.geometry, place, s)
                if len(panel_alphas) > 1:
                    angle = 2 * math.pi * alpha_index[alpha] / len(panel_alphas) + math.pi / 4
                    x, y = x + span * math.cos(angle), y + span * math.sin(angle)
                points.append((x, y))
                sizes.append(30 + 900 * count / self.max_agents)
                colors.append(self.colour[alpha])
                if self.max_agents <= 60 or count >= 0.015 * self.max_agents:
                    r, g, b, _ = self.colour[alpha]
                    ink = "black" if 0.299 * r + 0.587 * g + 0.114 * b > 0.6 else "white"
                    store["labels"].append(ax.text(x, y, str(count), fontsize=7.5, ha="center", va="center",
                                                   color=ink, weight="bold", zorder=6))
            for node, count in arrived.items():
                x, y = self.pos[node]
                store["labels"].append(ax.text(x, y - self.offset * 2.2, f"✓{count}", fontsize=8,
                                               ha="center", va="top", color="#b71c1c", zorder=6))
            for node, count in waiting.items():
                x, y = self.pos[node]
                store["labels"].append(ax.text(x, y + self.offset * 2.2, f"waiting {count}", fontsize=7.5,
                                               ha="center", va="bottom", color="#2e7d32", zorder=6))
            store["agents"].set_offsets(np.array(points) if points else np.empty((0, 2)))
            store["agents"].set_sizes(sizes)
            store["agents"].set_facecolors(colors)

            done = sum(arrived.values())
            shown = min(k, panel.steps)
            released = panel.n - sum(waiting.values())
            heats = f"released {released}/{panel.n}   " if panel.heats > 1 else ""
            store["status"].set_text(
                f"step {shown}/{panel.steps}   {heats}arrived {done}/{panel.n}   "
                f"avg cost so far {panel.cumulative_cost(t) / panel.n:.2f}"
            )
        self.fig.canvas.draw_idle()

    # ---------------------------------------------------------------- interactive window
    def show(self):
        from matplotlib.widgets import Button, Slider

        slider_ax = self.fig.add_axes([0.16, 0.115, 0.62, 0.025])
        button_ax = self.fig.add_axes([0.04, 0.105, 0.09, 0.045])
        self.slider = Slider(slider_ax, "time", 0, self.total_steps, valinit=0)
        self.button = Button(button_ax, "Play")
        self.slider.on_changed(self.draw)

        def toggle(_=None):
            if not self.playing and self.time >= self.total_steps - 1e-9:
                self.slider.set_val(0)
            self.playing = not self.playing
            self.button.label.set_text("Pause" if self.playing else "Play")

        def tick():
            if self.playing:
                t = min(self.time + 1 / self.fps_per_step, self.total_steps)
                self.slider.set_val(t)
                if t >= self.total_steps:
                    toggle()

        def on_key(event):
            if event.key == " ":
                toggle()
            elif event.key == "right":
                self.slider.set_val(min(math.floor(self.time + 1e-9) + 1, self.total_steps))
            elif event.key == "left":
                self.slider.set_val(max(math.ceil(self.time - 1e-9) - 1, 0))

        self.button.on_clicked(toggle)
        self.fig.canvas.mpl_connect("key_press_event", on_key)
        timer = self.fig.canvas.new_timer(interval=70)
        timer.add_callback(tick)
        timer.start()
        self.draw(0)
        plt.show()

    def save(self, path, fps=12):
        from matplotlib.animation import FFMpegWriter, FuncAnimation, PillowWriter

        hold = self.fps_per_step  # pause at the start and the end
        frames = [0.0] * hold + list(np.linspace(0, self.total_steps, self.total_steps * self.fps_per_step + 1))
        frames += [float(self.total_steps)] * hold * 2
        animation = FuncAnimation(self.fig, lambda t: self.draw(t), frames=frames, blit=False)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        writer = FFMpegWriter(fps=fps) if path.suffix.lower() == ".mp4" else PillowWriter(fps=fps)
        animation.save(path, writer=writer, dpi=90)
        print(f"Saved animation to {path}")

    def snapshot(self, t, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.draw(min(max(t, 0.0), self.total_steps))
        self.fig.savefig(path, dpi=130)
        print(f"Saved snapshot of t={t:g} to {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--population", action="append", default=None,
                        help="Information mix, e.g. '1', '0.5', '1:0.1,0'. Repeat for side-by-side panels. "
                             "Default: alphas from agents.json.")
    parser.add_argument("--seed", type=int, default=None, help="Override the scenario seed")
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--frames-per-step", type=int, default=10)
    parser.add_argument("--save", type=Path, default=None, help="Save animation (.gif or .mp4)")
    parser.add_argument("--snapshot", nargs=2, metavar=("TIME", "PATH"), default=None,
                        help="Save a still image at TIME (e.g. 1 or 1.5) to PATH")
    parser.add_argument("--no-show", action="store_true", help="Do not open a window")
    args = parser.parse_args()

    specs = args.population or [None]
    panels = [Panel(args.scenario, parse_population(spec), args.seed, args.max_steps) for spec in specs]
    viewer = Viewer(args.scenario, panels, fps_per_step=args.frames_per_step)

    if args.snapshot:
        viewer.snapshot(float(args.snapshot[0]), args.snapshot[1])
    if args.save:
        viewer.save(args.save)
    if not args.no_show:
        viewer.show()


if __name__ == "__main__":
    main()
