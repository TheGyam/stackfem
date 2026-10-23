"""Run one level, or every level of the mesh-convergence study."""

import csv
import time
from pathlib import Path

from . import mesh, quality, solver, stress


def run_level(p, level, out):
    """Mesh, check, solve and save one level into out/level_<n>. Returns its summary row."""
    folder = Path(out) / f"level_{level}"
    folder.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()

    data = mesh.generate(p, level, msh_path=folder / "mesh.msh")
    print(f"level {level}: {len(data['nodes'])} nodes")
    print(quality.table(data["quality"]))

    deck = folder / f"{p['name']}_thermal.inp"
    solver.write_deck(p, data, deck)
    data["temperature"] = solver.read_temperatures(solver.run(deck), len(data["nodes"]))
    row = {"level": level, **solver.summarise(p, data),
           "min_sicn": min(r["min_sicn"] for r in data["quality"].values())}
    print(f"level {level}: max temperature {row['t_max']:.3f} C, R_th {row['r_th']:.4f} K/W")

    if "mechanics" in p:
        deck = folder / f"{p['name']}_stress.inp"
        stress.write_deck(p, data, deck)
        stress.read(solver.run(deck), data)
        row.update(stress.summarise(p, data))
        print(f"level {level}: largest displacement {row['u_max']:.2f} um, "
              f"die-top bow {row['top_bow']:.3f} um")

    mesh.save(data, folder / "result.npz")
    row["seconds"] = round(time.perf_counter() - start, 1)
    print()
    return row


def run_all(p, out):
    rows = [run_level(p, level, out) for level in range(p["study"]["levels"])]
    write_summary(rows, Path(out) / "summary.csv")
    return rows


def write_summary(rows, path):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def read_summary(path):
    with open(path, newline="") as f:
        return [{k: float(v) for k, v in row.items()} for row in csv.DictReader(f)]
