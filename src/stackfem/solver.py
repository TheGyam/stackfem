"""CalculiX: the parts every deck shares, and the heat-flow step.

Units in the decks are mm, mW, N, MPa and degrees C. Conductivity in W/(m K) is
the same number in mW/(mm K), so it goes in unchanged; power is converted from W
to mW and the film coefficient from W/(m2 K) to mW/(mm2 K).
"""

import os
import shutil
import subprocess

import numpy as np

# Gmsh and CalculiX number the tet10 mid-edge nodes differently: the last two swap.
GMSH_TO_CCX = [0, 1, 2, 3, 4, 5, 6, 7, 9, 8]
# CalculiX's faces of a tetrahedron, F1 to F4, by corner node.
FACES = [(0, 1, 2), (0, 3, 1), (1, 3, 2), (2, 3, 0)]
# The iterative solver matches the default direct one (spooles) to the printed
# precision on these meshes and is several times faster.
SOLVER = "SOLVER=ITERATIVE CHOLESKY"


def write_mesh(f, p, data, material_cards):
    """Nodes, elements (one ELSET per layer), the BOTTOM node set, materials and sections.

    `material_cards(material)` returns the material's property cards as text.
    Elements are numbered from 1 through the layers in stack order.
    """
    f.write(f"*HEADING\nstackfem {p['name']}\n")
    f.write("*NODE, NSET=NALL\n")
    for i, (x, y, z) in enumerate(data["nodes"], start=1):
        f.write(f"{i}, {x:.9g}, {y:.9g}, {z:.9g}\n")
    next_id = 1
    for name, conn in data["elements"].items():
        f.write(f"*ELEMENT, TYPE=C3D10, ELSET={name}\n")
        for row in conn[:, GMSH_TO_CCX]:
            f.write(f"{next_id}, " + ", ".join(map(str, row)) + "\n")
            next_id += 1
    f.write("*NSET, NSET=BOTTOM\n")
    write_ids(f, data["bottom"])
    used = {layer["material"] for layer in p["layer"]}
    for name in sorted(used):
        f.write(f"*MATERIAL, NAME={name}\n" + material_cards(p["material"][name]))
    for layer in p["layer"]:
        f.write(f"*SOLID SECTION, ELSET={layer['name']}, MATERIAL={layer['material']}\n")


def write_ids(f, ids, per_line=12):
    for i in range(0, len(ids), per_line):
        f.write(", ".join(map(str, ids[i:i + per_line])) + "\n")


def write_deck(p, data, path):
    """The heat-flow deck: heat made in the source layer, leaving through the bottom."""
    load = p["load"]
    with open(path, "w") as f:
        write_mesh(f, p, data, lambda m: f"*CONDUCTIVITY\n{m['conductivity']}\n")
        f.write(f"*INITIAL CONDITIONS, TYPE=TEMPERATURE\nNALL, {load['sink']}\n")
        f.write(f"*STEP\n*HEAT TRANSFER, STEADY STATE, {SOLVER}\n1., 1.\n")
        if "film" in load:
            f.write("*FILM\n")
            for element, face in bottom_faces(data):
                f.write(f"{element}, F{face}, {load['sink']}, {load['film'] * 1e-3:.9g}\n")
        else:
            f.write(f"*BOUNDARY\nBOTTOM, 11, 11, {load['sink']}\n")
        f.write(f"*DFLUX\n{load['source']}, BF, {heat_density(p):.9g}\n")
        f.write("*NODE PRINT, NSET=NALL\nNT\n*NODE FILE\nNT\n*END STEP\n")


def bottom_faces(data):
    """(element id, face number) for every element face lying on the bottom."""
    on_bottom = np.zeros(len(data["nodes"]) + 1, bool)
    on_bottom[data["bottom"]] = True
    corners = np.vstack(list(data["elements"].values()))[:, :4]
    found = []
    for number, face in enumerate(FACES, start=1):
        hit = np.flatnonzero(on_bottom[corners[:, face]].all(axis=1))
        found += [(e + 1, number) for e in hit]
    return sorted(found)


def heat_density(p):
    """Power per unit volume in the source layer, mW/mm^3."""
    layer = next(l for l in p["layer"] if l["name"] == p["load"]["source"])
    volume = layer["size"][0] * layer["size"][1] * layer["thickness"]
    return p["load"]["power"] * 1000 / volume


def find_ccx():
    exe = os.environ.get("STACKFEM_CCX") or shutil.which("ccx") or shutil.which("ccx_static")
    if not exe:
        raise FileNotFoundError(
            "CalculiX (ccx) was not found. Put it on PATH or set STACKFEM_CCX to its full path.")
    return exe


def run(deck):
    """Run ccx on `deck` (a .inp path) in its own folder. Returns the .dat path."""
    deck = os.path.abspath(deck)
    folder, job = os.path.dirname(deck), os.path.splitext(os.path.basename(deck))[0]
    env = dict(os.environ)
    env.setdefault("OMP_NUM_THREADS", str(os.cpu_count() or 1))
    log_path = os.path.join(folder, f"{job}.log")
    with open(log_path, "w") as log:
        done = subprocess.run([find_ccx(), "-i", job], cwd=folder, env=env,
                              stdout=log, stderr=subprocess.STDOUT)
    if done.returncode != 0:
        raise RuntimeError(f"ccx failed (exit {done.returncode}); see {log_path}")
    return os.path.join(folder, job + ".dat")


def read_dat(dat):
    """Every printed block of a .dat file: {(quantity, set name): rows as an array}.

    A block starts with a line like " temperatures for set NALL and time 1.0" and
    holds one row of numbers per node or integration point. If ccx printed several
    increments, the last one wins.
    """
    blocks, current = {}, None
    with open(dat) as f:
        for line in f:
            if " for set " in line:
                words = line.split()
                current = (words[0], words[words.index("set") + 1].lower())
                blocks[current] = []
            elif current and line.strip():
                blocks[current].append([float(x) for x in line.split()])
    return {key: np.array(rows) for key, rows in blocks.items()}


def read_temperatures(dat, n_nodes):
    """Nodal temperatures, indexed by node id - 1."""
    rows = read_dat(dat)[("temperatures", "nall")]
    t = np.full(n_nodes, np.nan)
    t[rows[:, 0].astype(int) - 1] = rows[:, 1]
    if np.isnan(t).any():
        raise RuntimeError(f"{dat} is missing temperatures for {np.isnan(t).sum()} nodes")
    return t


def summarise(p, data):
    """The heat-flow numbers the study tracks for one solved mesh."""
    source = np.unique(data["elements"][p["load"]["source"]])
    t_max = float(data["temperature"][source - 1].max())
    return {
        "nodes": len(data["nodes"]),
        "elements": sum(len(e) for e in data["elements"].values()),
        "t_max": t_max,
        "r_th": (t_max - p["load"]["sink"]) / p["load"]["power"],
    }
