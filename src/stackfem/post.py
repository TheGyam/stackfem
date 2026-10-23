"""Turn a results folder into a convergence table and plots.

Works on any folder written by `stackfem run` or `stackfem study`, so it can be
re-run on its own after changing a plot.
"""

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from . import mesh, study  # noqa: E402
from .params import layer_heights  # noqa: E402

INK, MUTED, LINE, BAND = "#1f2328", "#59636e", "#2f6fb5", "#eef1f4"


def richardson(h, phi):
    """Extrapolate a result to zero element size from the three finest meshes.

    Follows Celik et al. (2008), the procedure ASME V&V 20 uses: works with
    unequal refinement ratios. `h` is a representative element size per mesh and
    `phi` the result on it, in any order. Returns the observed order p, the
    extrapolated value, and the fine-mesh grid convergence index (GCI, a relative
    error band with a 1.25 safety factor).
    """
    (h1, f1), (h2, f2), (h3, f3) = sorted(zip(h, phi))[:3]
    r21, r32 = h2 / h1, h3 / h2
    e21, e32 = f2 - f1, f3 - f2
    if e21 == 0 or e32 == 0:
        return {"order": math.nan, "extrapolated": f1, "gci": 0.0}
    s = math.copysign(1, e32 / e21)
    p = 0.0
    for _ in range(100):  # fixed-point iteration; converges in a few steps
        q = math.log((r21 ** p - s) / (r32 ** p - s)) if p else 0.0
        p_new = abs(math.log(abs(e32 / e21)) + q) / math.log(r21)
        if abs(p_new - p) < 1e-10:
            break
        p = p_new
    extrapolated = (r21 ** p * f1 - f2) / (r21 ** p - 1)
    gci = 1.25 * abs((f1 - f2) / f1) / (r21 ** p - 1)
    return {"order": p, "extrapolated": extrapolated, "gci": gci}


def element_size(p, nodes):
    """Representative element size: (stack volume / nodes) ** (1/3), in mm."""
    volume = sum(l["size"][0] * l["size"][1] * l["thickness"] for l in p["layer"])
    return (volume / np.asarray(nodes, float)) ** (1 / 3)


def style(ax):
    ax.grid(True, color="#d0d7de", linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=MUTED)
    ax.xaxis.label.set_color(INK)
    ax.yaxis.label.set_color(INK)
    ax.title.set_color(INK)


def plot_convergence(p, rows, path):
    h = element_size(p, [r["nodes"] for r in rows])
    t = [r["t_max"] for r in rows]
    fit = richardson(h, t) if len(rows) >= 3 else None

    fig, ax = plt.subplots(figsize=(6.4, 4.2), dpi=150)
    ax.plot(h, t, "-o", color=LINE, linewidth=2, markersize=6, label="CalculiX")
    for hi, ti, r in zip(h, t, rows):
        ax.annotate(f"level {int(r['level'])}", (hi, ti), textcoords="offset points",
                    xytext=(6, 6), fontsize=8, color=MUTED)
    if fit:
        ax.axhline(fit["extrapolated"], color=MUTED, linestyle="--", linewidth=1,
                   label=f"extrapolated {fit['extrapolated']:.3f} °C")
        ax.set_title(f"Max die temperature: observed order {fit['order']:.2f}, "
                     f"GCI {fit['gci']:.2%}", fontsize=10)
    else:
        ax.set_title("Max die temperature", fontsize=10)
    ax.set_xlabel("element size, (volume / nodes)$^{1/3}$  [mm]")
    ax.set_ylabel("max die temperature  [°C]")
    ax.set_xlim(left=0)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK)
    style(ax)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return fit


# Gmsh's tet10 mid-edge nodes 4..9 sit on these corner pairs.
EDGES = [(0, 1), (1, 2), (0, 2), (0, 3), (2, 3), (1, 3)]


def probe(data, points):
    """Temperature at arbitrary points, using the element's own quadratic shape functions.

    Points outside the mesh come back as NaN.
    """
    nodes, t = data["nodes"], data["temperature"]
    conn = np.vstack(list(data["elements"].values())) - 1
    corners = nodes[conn[:, :4]]
    lo, hi = corners.min(axis=1) - 1e-9, corners.max(axis=1) + 1e-9
    out = np.full(len(points), np.nan)
    for i, x in enumerate(np.asarray(points, float)):
        for e in np.flatnonzero(np.all((lo <= x) & (x <= hi), axis=1)):
            v = corners[e]
            lam = np.linalg.solve((v[1:] - v[0]).T, x - v[0])
            L = np.concatenate([[1 - lam.sum()], lam])
            if L.min() >= -1e-9:
                shape = np.concatenate([L * (2 * L - 1), [4 * L[a] * L[b] for a, b in EDGES]])
                out[i] = shape @ t[conn[e]]
                break
    return out


def spread(ys, gap):
    """Nudge label heights apart so no two are closer than `gap`."""
    ys = list(ys)
    for i in range(1, len(ys)):
        ys[i] = max(ys[i], ys[i - 1] + gap)
    return ys


def plot_profile(p, data, path):
    """Temperature against height along the stack's centre line."""
    heights = layer_heights(p)
    top = heights[-1][1]
    z = np.unique(np.concatenate([np.linspace(z0, z1, 40) for z0, z1 in heights]))
    t = probe(data, np.column_stack([np.zeros_like(z), np.zeros_like(z), z]))

    fig, ax = plt.subplots(figsize=(6.4, 4.2), dpi=150)
    for z0, _ in heights[1:]:
        ax.axhline(z0, color="#d0d7de", linewidth=0.8)
    for layer, y in zip(p["layer"], spread([(z0 + z1) / 2 for z0, z1 in heights], 0.06 * top)):
        ax.text(1.01, y, layer["name"], transform=ax.get_yaxis_transform(),
                fontsize=8, color=MUTED, va="center")
    ax.plot(t, z, color=LINE, linewidth=2)
    ax.set_xlabel("temperature  [°C]")
    ax.set_ylabel("height  [mm]")
    ax.set_title("Temperature along the centre line", fontsize=10)
    ax.set_ylim(0, top)
    style(ax)
    ax.grid(False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_top(p, data, path):
    """Temperature map over the top face of the stack."""
    nodes, t = data["nodes"], data["temperature"]
    top = np.isclose(nodes[:, 2], layer_heights(p)[-1][1])

    fig, ax = plt.subplots(figsize=(5.4, 4.4), dpi=150)
    filled = ax.tricontourf(nodes[top, 0], nodes[top, 1], t[top], levels=20, cmap="Reds")
    bar = fig.colorbar(filled, ax=ax)
    bar.set_label("temperature  [°C]", color=INK)
    ax.set_aspect("equal")
    ax.set_xlabel("x  [mm]")
    ax.set_ylabel("y  [mm]")
    ax.set_title(f"Top of the {p['layer'][-1]['name']}", fontsize=10)
    style(ax)
    ax.grid(False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def report(p, out):
    """Write every plot and the convergence numbers for a results folder."""
    out = Path(out)
    rows = study.read_summary(out / "summary.csv")
    finest = mesh.load(out / f"level_{int(rows[-1]['level'])}" / "result.npz")

    fit = plot_convergence(p, rows, out / "convergence.png")
    plot_profile(p, finest, out / "profile.png")
    plot_top(p, finest, out / "top.png")

    lines = [f"{'level':>5}{'nodes':>10}{'h [mm]':>9}{'T max [C]':>11}{'R_th [K/W]':>12}"]
    for r, h in zip(rows, element_size(p, [r["nodes"] for r in rows])):
        lines.append(f"{int(r['level']):>5}{int(r['nodes']):>10}{h:>9.4f}{r['t_max']:>11.3f}{r['r_th']:>12.4f}")
    if fit:
        lines.append(f"\nobserved order {fit['order']:.2f}, extrapolated T max "
                     f"{fit['extrapolated']:.3f} C, GCI on the finest mesh {fit['gci']:.3%}")
    text = "\n".join(lines)
    (out / "convergence.txt").write_text(text + "\n")
    return text
