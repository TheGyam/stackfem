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
from .stress import element_volumes  # noqa: E402
from .params import layer_heights  # noqa: E402

INK, MUTED, LINE = "#1f2328", "#59636e", "#2f6fb5"


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


# Categorical colours for the per-layer stress lines, in a fixed order.
SERIES = ["#2f6fb5", "#d9822b", "#2e9e6a", "#b5459a", "#7d6ac9", "#c9a227", "#5b6770"]


def tracked(rows):
    """(column, name, unit) of each converging result in the study. Peak stresses are
    left out on purpose: they sit on edge singularities and never converge."""
    out = [("t_max", "max die temperature", "°C")]
    if "u_max" in rows[0]:
        out.append(("u_max", "largest displacement", "µm"))
        out += [(k, f"mean stress, {k[len('vm_mean_'):]}", "MPa") for k in rows[0] if k.startswith("vm_mean_")]
    return out


def fits(p, rows):
    """Richardson extrapolation of every tracked result, if there are three levels."""
    if len(rows) < 3:
        return {}
    h = element_size(p, [r["nodes"] for r in rows])
    return {key: richardson(h, [r[key] for r in rows]) for key, _, _ in tracked(rows)}


def plot_convergence(p, rows, fitted, path):
    """One panel per kind of result, all against element size.

    Temperature and displacement are shown as they are. The layer stresses differ
    by an order of magnitude, so they share a panel as a change from the finest mesh.
    """
    h = element_size(p, [r["nodes"] for r in rows])
    stresses = [(k, n) for k, n, _ in tracked(rows) if k.startswith("vm_mean_")]
    singles = [t for t in tracked(rows) if not t[0].startswith("vm_mean_")]
    panels = len(singles) + bool(stresses)
    fig, axes = plt.subplots(1, panels, figsize=(4.6 * panels, 3.8), dpi=150, squeeze=False)

    for ax, (key, name, unit) in zip(axes[0], singles):
        values = [r[key] for r in rows]
        ax.plot(h, values, "-o", color=LINE, linewidth=2, markersize=6)
        for hi, v, r in zip(h, values, rows):
            ax.annotate(f"level {int(r['level'])}", (hi, v), textcoords="offset points",
                        xytext=(6, 6), fontsize=8, color=MUTED)
        fit = fitted.get(key)
        if fit:
            ax.axhline(fit["extrapolated"], color=MUTED, linestyle="--", linewidth=1,
                       label=f"extrapolated {fit['extrapolated']:.5g} {unit}")
            ax.legend(frameon=False, fontsize=8, labelcolor=INK)
            ax.set_title(f"{name.capitalize()}\norder {fit['order']:.2f}, GCI {fit['gci']:.2%}", fontsize=10)
        else:
            ax.set_title(name.capitalize(), fontsize=10)
        ax.set_ylabel(f"{name}  [{unit}]")

    if stresses:
        ax = axes[0][-1]
        for (key, name), colour in zip(stresses, SERIES):
            values = np.array([r[key] for r in rows])
            ax.plot(h, 100 * (values / values[-1] - 1), "-o", color=colour, linewidth=2,
                    markersize=5, label=name.split(", ")[1])
        ax.axhline(0, color=MUTED, linewidth=0.8)
        ax.set_title("Mean stress per layer", fontsize=10)
        ax.set_ylabel("change from the finest mesh  [%]")
        ax.legend(frameon=False, fontsize=8, labelcolor=INK)

    for ax in axes[0]:
        ax.set_xlabel("element size  [mm]")
        ax.set_xlim(left=0)
        style(ax)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_stress(p, data, path):
    """Mean and peak von Mises stress in each layer, on the finest mesh."""
    names = [l["name"] for l in p["layer"]]
    mean = [np.average(data["von_mises"][n], weights=element_volumes(data["nodes"], data["elements"][n]))
            for n in names]
    peak = [data["von_mises_peak"][n].max() for n in names]
    y = np.arange(len(names))

    fig, ax = plt.subplots(figsize=(6.4, 0.6 * len(names) + 1.4), dpi=150)
    ax.barh(y, mean, height=0.5, color=LINE, label="mean over the layer")
    ax.plot(peak, y, "o", color=SERIES[1], markersize=8, label="peak, at an edge (grows with refinement)")
    for yi, m in zip(y, mean):
        ax.text(m, yi, f" {m:.1f}", va="center", fontsize=8, color=INK)
    ax.set_yticks(y, names)
    ax.invert_yaxis()
    ax.set_xlabel("von Mises stress  [MPa]")
    ax.set_title("Thermal stress by layer", fontsize=10)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK, loc="lower right")
    style(ax)
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


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

    fitted = fits(p, rows)
    plot_convergence(p, rows, fitted, out / "convergence.png")
    plot_profile(p, finest, out / "profile.png")
    plot_top(p, finest, out / "top.png")
    if "von_mises" in finest:
        plot_stress(p, finest, out / "stress.png")

    lines = [f"{'level':>5}{'nodes':>10}{'h [mm]':>9}{'T max [C]':>11}{'R_th [K/W]':>12}"]
    for r, h in zip(rows, element_size(p, [r["nodes"] for r in rows])):
        lines.append(f"{int(r['level']):>5}{int(r['nodes']):>10}{h:>9.4f}{r['t_max']:>11.3f}{r['r_th']:>12.4f}")
    if "u_max" in rows[0]:
        names = [l["name"] for l in p["layer"]]
        lines.append("\nlargest displacement [um] and mean / peak von Mises stress [MPa]")
        lines.append(f"{'level':>5}{'u max':>9}" + "".join(f"{n:>22}" for n in names))
        for r in rows:
            cells = "".join(f"{r[f'vm_mean_{n}']:>12.2f} / {r[f'vm_peak_{n}']:<7.1f}" for n in names)
            lines.append(f"{int(r['level']):>5}{r['u_max']:>9.3f}{cells}")
    if fitted:
        lines.append("\nextrapolated to zero element size:")
        for key, name, unit in tracked(rows):
            fit = fitted[key]
            unit = unit.replace("\u00b0C", "C").replace("\u00b5m", "um")  # plain text for any console
            lines.append(f"  {name:<30}{fit['extrapolated']:>10.5g} {unit:<4} order {fit['order']:5.2f}, "
                         f"GCI on the finest mesh {fit['gci']:.3%}")
    text = "\n".join(lines)
    (out / "convergence.txt").write_text(text + "\n", encoding="utf-8")
    return text
