"""The thermal stress step: the temperatures from the heat-flow run, applied to an
elastic stack.

Stiffness is entered in GPa and written in MPa (N/mm2), so stresses come out in
MPa and displacements in mm. Expansion is entered in ppm/K.
"""

import numpy as np

from .params import layer_heights
from .solver import read_dat, write_mesh

# Unlike the heat flow, the stress step is sensitive to the iterative solver's
# stopping point: on a stack that should carry no stress it leaves stresses of
# about 0.5% of the thermal stress scale, where the direct solver leaves none.
# The direct solver needs far more memory on big meshes.
SOLVERS = {"direct": "SOLVER=SPOOLES", "iterative": "SOLVER=ITERATIVE CHOLESKY"}


def material_cards(m):
    return (f"*ELASTIC\n{m['youngs_modulus'] * 1000:.9g}, {m['poisson']}\n"
            f"*EXPANSION\n{m['expansion'] * 1e-6:.9g}\n")


def supports(p, data):
    """Displacement constraints as (node id, first dof, last dof).

    Three bottom nodes stop rigid-body motion without stopping free expansion:
    A, nearest the centre, cannot move sideways; B, towards the +x edge, cannot
    move in y, so the stack cannot spin. "flat" also holds the whole bottom at
    z = 0. "free" instead holds A, B and a third node C, towards the +y edge, in
    z, which leaves the stack free to bow.
    """
    bottom = data["bottom"]
    xyz = data["nodes"][bottom - 1]

    def nearest(x, y):
        return int(bottom[np.argmin(np.hypot(xyz[:, 0] - x, xyz[:, 1] - y))])

    lx, ly = p["layer"][0]["size"]
    a, b, c = nearest(0, 0), nearest(lx / 2, 0), nearest(0, ly / 2)
    if p["mechanics"]["support"] == "flat":
        return [("BOTTOM", 3, 3), (a, 1, 2), (b, 2, 2)]
    return [(a, 1, 3), (b, 2, 3), (c, 3, 3)]


def write_deck(p, data, path):
    with open(path, "w") as f:
        write_mesh(f, p, data, material_cards)
        f.write(f"*INITIAL CONDITIONS, TYPE=TEMPERATURE\nNALL, {p['mechanics']['stress_free']}\n")
        f.write("*BOUNDARY\n")
        for node, first, last in supports(p, data):
            f.write(f"{node}, {first}, {last}\n")
        f.write(f"*STEP\n*STATIC, {SOLVERS[p['mechanics'].get('solver', 'direct')]}\n*TEMPERATURE\n")
        for i, t in enumerate(data["temperature"], start=1):
            f.write(f"{i}, {t:.9g}\n")
        f.write("*NODE PRINT, NSET=NALL\nU\n")
        for layer in p["layer"]:
            f.write(f"*EL PRINT, ELSET={layer['name']}\nS\n")
        f.write("*NODE FILE\nU, NT\n*EL FILE\nS\n*END STEP\n")


def von_mises(s):
    """Von Mises stress from rows of (sxx, syy, szz, sxy, sxz, syz)."""
    sxx, syy, szz, sxy, sxz, syz = s.T
    return np.sqrt(0.5 * ((sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2)
                   + 3 * (sxy ** 2 + sxz ** 2 + syz ** 2))


def read(dat, data):
    """Add `displacement` (N, 3) and per-layer von Mises stress to `data`.

    von_mises[layer]       (M,) the element's mean over its integration points
    von_mises_peak[layer]  (M,) the element's highest integration point
    """
    blocks = read_dat(dat)
    rows = blocks[("displacements", "nall")]
    u = np.zeros((len(data["nodes"]), 3))
    u[rows[:, 0].astype(int) - 1] = rows[:, 1:4]
    data["displacement"] = u

    data["von_mises"], data["von_mises_peak"] = {}, {}
    for name, conn in data["elements"].items():
        rows = blocks[("stresses", name.lower())]
        rows = rows[np.lexsort((rows[:, 1], rows[:, 0]))]  # by element, then point
        points = von_mises(rows[:, 2:8]).reshape(len(conn), -1)
        data["von_mises"][name] = points.mean(axis=1)
        data["von_mises_peak"][name] = points.max(axis=1)
    return data


def element_volumes(nodes, conn):
    a, b, c, d = (nodes[conn[:, i] - 1] for i in range(4))
    return np.einsum("ij,ij->i", b - a, np.cross(c - a, d - a)) / 6


def summarise(p, data):
    """The stress numbers the study tracks: displacements in um, stresses in MPa.

    Mean stress is volume-weighted over the layer. Peak stress sits at the sharp
    edges where layers of different stiffness meet; in an elastic model it is
    infinite there, so it keeps rising as the mesh is refined. Use it to see where
    stress gathers, not as a converged number.
    """
    u = data["displacement"]
    top = np.isclose(data["nodes"][:, 2], layer_heights(p)[-1][1])
    row = {
        "u_max": float(np.linalg.norm(u, axis=1).max() * 1000),
        "top_bow": float(np.ptp(u[top, 2]) * 1000),
    }
    for name, conn in data["elements"].items():
        weights = element_volumes(data["nodes"], conn)
        row[f"vm_mean_{name}"] = float(np.average(data["von_mises"][name], weights=weights))
        row[f"vm_peak_{name}"] = float(data["von_mises_peak"][name].max())
    return row
