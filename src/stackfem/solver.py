"""Write a CalculiX input deck, run ccx, and read the temperatures back.

Units in the deck are mm, mW and degrees C. Conductivity in W/(m K) is the same
number in mW/(mm K), so it goes in unchanged; power is converted from W to mW.
"""

import os
import shutil
import subprocess

import numpy as np

# Gmsh and CalculiX number the tet10 mid-edge nodes differently: the last two swap.
GMSH_TO_CCX = [0, 1, 2, 3, 4, 5, 6, 7, 9, 8]


def write_deck(p, data, path):
    nodes, elements = data["nodes"], data["elements"]
    load = p["load"]
    materials = {layer["name"]: layer["material"] for layer in p["layer"]}
    with open(path, "w") as f:
        f.write(f"*HEADING\nstackfem {p['name']}\n")
        f.write("*NODE, NSET=NALL\n")
        for i, (x, y, z) in enumerate(nodes, start=1):
            f.write(f"{i}, {x:.9g}, {y:.9g}, {z:.9g}\n")

        next_id = 1
        for name, conn in elements.items():
            f.write(f"*ELEMENT, TYPE=C3D10, ELSET={name}\n")
            for row in conn[:, GMSH_TO_CCX]:
                f.write(f"{next_id}, " + ", ".join(map(str, row)) + "\n")
                next_id += 1

        f.write("*NSET, NSET=COLD\n")
        write_ids(f, data["cold"])

        for name, material in p["material"].items():
            f.write(f"*MATERIAL, NAME={name}\n*CONDUCTIVITY\n{material['conductivity']}\n")
        for name, material in materials.items():
            f.write(f"*SOLID SECTION, ELSET={name}, MATERIAL={material}\n")

        f.write(f"*INITIAL CONDITIONS, TYPE=TEMPERATURE\nNALL, {load['cold_plate']}\n")
        # The iterative solver matches the default direct one (spooles) to the printed
        # precision on these meshes and is several times faster.
        f.write("*STEP\n*HEAT TRANSFER, STEADY STATE, SOLVER=ITERATIVE CHOLESKY\n1., 1.\n")
        f.write(f"*BOUNDARY\nCOLD, 11, 11, {load['cold_plate']}\n")
        f.write(f"*DFLUX\n{load['source']}, BF, {heat_density(p):.9g}\n")
        f.write("*NODE PRINT, NSET=NALL\nNT\n*NODE FILE\nNT\n*END STEP\n")


def write_ids(f, ids, per_line=12):
    for i in range(0, len(ids), per_line):
        f.write(", ".join(map(str, ids[i:i + per_line])) + "\n")


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
    with open(os.path.join(folder, "ccx.log"), "w") as log:
        done = subprocess.run([find_ccx(), "-i", job], cwd=folder, env=env,
                              stdout=log, stderr=subprocess.STDOUT)
    if done.returncode != 0:
        raise RuntimeError(f"ccx failed (exit {done.returncode}); see {os.path.join(folder, 'ccx.log')}")
    return os.path.join(folder, job + ".dat")


def read_temperatures(dat, n_nodes):
    """Temperatures from the NODE PRINT block of a .dat file, indexed by node id - 1.

    If ccx printed several increments, the last one wins.
    """
    t = np.full(n_nodes, np.nan)
    with open(dat) as f:
        for line in f:
            parts = line.split()
            if len(parts) == 2 and parts[0].isdigit():
                t[int(parts[0]) - 1] = float(parts[1])
    if np.isnan(t).any():
        raise RuntimeError(f"{dat} is missing temperatures for {np.isnan(t).sum()} nodes")
    return t


def summarise(p, data):
    """The numbers the study tracks for one solved mesh."""
    source = np.unique(data["elements"][p["load"]["source"]])
    t_max = float(data["temperature"][source - 1].max())
    return {
        "nodes": len(data["nodes"]),
        "elements": sum(len(e) for e in data["elements"].values()),
        "t_max": t_max,
        "r_th": (t_max - p["load"]["cold_plate"]) / p["load"]["power"],
    }
