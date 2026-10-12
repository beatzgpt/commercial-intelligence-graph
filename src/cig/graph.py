"""Build the knowledge graph from SQLite and draw two views (account ego graph, segment map)."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx  # noqa: E402

ROLE_LABEL = {"economic_buyer": "buyer", "champion": "champion",
              "technical_evaluator": "evaluator", "security_blocker": "gatekeeper"}
COLORS = {"company": "#1f3a5f", "person": "#2a9d8f", "legacy": "#c0392b",
          "modern": "#3a86c8", "signal": "#b8860b"}


def build_graph(conn) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    for r in conn.execute("SELECT * FROM companies"):
        g.add_node(r["company_id"], kind="company", label=r["name"], segment=r["segment"])
    for r in conn.execute("SELECT * FROM people"):
        g.add_node(r["person_id"], kind="person", label=r["name"], role=r["role_type"], title=r["title"])
        g.add_edge(r["person_id"], r["company_id"], rel="works_at")
    for r in conn.execute("SELECT * FROM technologies"):
        g.add_node(r["tech_id"], kind="tech", label=r["name"], generation=r["generation"])
    for r in conn.execute("SELECT * FROM company_technologies"):
        g.add_edge(r["company_id"], r["tech_id"], rel="uses", since=r["since"])
    for r in conn.execute("SELECT * FROM signals"):
        g.add_node(r["signal_id"], kind="signal", label=r["type"], source_id=r["source_id"],
                   observed_at=r["observed_at"])
        g.add_edge(r["signal_id"], r["company_id"], rel="observed_at_company", signal_id=r["signal_id"])
        if r["tech_id"]:
            g.add_edge(r["signal_id"], r["tech_id"], rel="mentions_tech", signal_id=r["signal_id"])
        if r["person_id"]:
            g.add_edge(r["signal_id"], r["person_id"], rel="mentions_person", signal_id=r["signal_id"])
    return g


def _node_style(g, n):
    d = g.nodes[n]
    if d["kind"] == "tech":
        return COLORS[d["generation"]], "s", 900
    return COLORS[d["kind"]], {"company": "o", "person": "o", "signal": "D"}[d["kind"]], \
        {"company": 2600, "person": 1100, "signal": 500}[d["kind"]]


def _label(g, n):
    d = g.nodes[n]
    if d["kind"] == "person":
        return f"{d['label']}\n({ROLE_LABEL.get(d['role'], d['role'])})"
    if d["kind"] == "signal":
        return f"{d['label']}\n{n}"
    return d["label"]


def draw_account_graph(g: nx.MultiDiGraph, company_id: str, path: Path, score: float | None = None) -> Path:
    nodes = {company_id}
    for u, v in g.in_edges(company_id):
        nodes.add(u)
    for u, v in g.out_edges(company_id):
        nodes.add(v)
    for n in list(nodes):
        if g.nodes[n]["kind"] == "signal":
            nodes.update(v for _, v in g.out_edges(n))
    sub = nx.Graph(g.subgraph(nodes))
    pos = nx.spring_layout(sub, seed=7, k=1.1, iterations=200)

    fig, ax = plt.subplots(figsize=(13, 8.5))
    nx.draw_networkx_edges(sub, pos, ax=ax, edge_color="#9aa5b1", width=1.2, alpha=0.8)
    for n in sub.nodes:
        color, marker, size = _node_style(g, n)
        ax.scatter(*pos[n], s=size, c=color, marker=marker, zorder=3, edgecolors="white", linewidths=1.5)
        ax.annotate(_label(g, n), pos[n], xytext=(0, -(size ** 0.5) / 2 - 10), textcoords="offset points",
                    ha="center", va="top", fontsize=8.5, color="#1b1f24")
    title = f"{g.nodes[company_id]['label']}: account graph (synthetic data)"
    if score is not None:
        title += f"  |  opportunity score {score}"
    ax.set_title(title, fontsize=13, loc="left", color="#1b1f24")
    handles = [plt.Line2D([], [], marker="o", ls="", color=COLORS["company"], label="company"),
               plt.Line2D([], [], marker="o", ls="", color=COLORS["person"], label="person"),
               plt.Line2D([], [], marker="s", ls="", color=COLORS["legacy"], label="legacy tech"),
               plt.Line2D([], [], marker="s", ls="", color=COLORS["modern"], label="modern tech"),
               plt.Line2D([], [], marker="D", ls="", color=COLORS["signal"], label="signal")]
    ax.legend(handles=handles, loc="lower left", frameon=False, fontsize=9, ncol=5)
    ax.margins(0.12)
    ax.axis("off")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140, bbox_inches="tight", facecolor="white", metadata={"Software": None})
    plt.close(fig)
    return path


def _wrap(text, width=18):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return "\n".join(lines + [cur])


def draw_segment_map(g: nx.MultiDiGraph, ranked: list[dict], segment: str, path: Path) -> Path:
    """Two-row layout: companies (by score) on top, the technologies they run below."""
    scores = {r["company"]["company_id"]: r["total"] for r in ranked}
    comps = list(scores)
    uses = [(c, v) for c in comps for _, v, d in g.out_edges(c, data=True) if d.get("rel") == "uses"]
    # order technologies by the average x-position of their companies to reduce edge crossings
    comp_x = {c: i for i, c in enumerate(comps)}
    tech_ids = sorted({v for _, v in uses}, key=lambda t: (sum(comp_x[c] for c, v in uses if v == t) / sum(1 for _, v in uses if v == t), t))
    span = max(len(comps), len(tech_ids))
    cx = {c: (i + 0.5) * span / len(comps) for i, c in enumerate(comps)}
    tx = {t: (i + 0.5) * span / len(tech_ids) for i, t in enumerate(tech_ids)}

    fig, ax = plt.subplots(figsize=(14, 7.5))
    for c, t in uses:
        ax.plot([cx[c], tx[t]], [1, 0], color="#c3cad3", lw=1.1, zorder=1)
    top = max(scores.values()) or 1
    for c in comps:
        frac = scores[c] / top
        ax.scatter(cx[c], 1, s=500 + 2600 * frac, zorder=3, edgecolors="white", linewidths=1.5,
                   c=[(0.12, 0.23 + 0.4 * (1 - frac), 0.37 + 0.45 * (1 - frac))])
        ax.annotate(f"{_wrap(g.nodes[c]['label'])}\nscore {scores[c]}", (cx[c], 1), xytext=(0, 30 + 28 * frac),
                    textcoords="offset points", ha="center", va="bottom", fontsize=8.5)
    for t in tech_ids:
        color, marker, size = _node_style(g, t)
        ax.scatter(tx[t], 0, s=size * 0.7, c=color, marker=marker, zorder=3, edgecolors="white")
        ax.annotate(_wrap(g.nodes[t]["label"], 16), (tx[t], 0), xytext=(0, -16), textcoords="offset points",
                    ha="center", va="top", fontsize=8, color="#5b6573")
    ax.set_title(f"Market map: {segment} (synthetic data). Circle size and darkness = opportunity score. "
                 "Red = legacy tech, blue = modern", fontsize=12, loc="left")
    ax.set_ylim(-0.35, 1.45)
    ax.margins(x=0.06)
    ax.axis("off")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140, bbox_inches="tight", facecolor="white", metadata={"Software": None})
    plt.close(fig)
    return path
