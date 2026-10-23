"""Element quality checks, run on every mesh before it reaches the solver."""

import gmsh
import numpy as np

TET10 = 11  # Gmsh's element type number for the 10-node tetrahedron


class QualityError(RuntimeError):
    pass


def check(p, volumes):
    """Measure every layer's elements and raise QualityError if the mesh is too poor.

    Uses Gmsh's minimum scaled Jacobian (SICN) and the inscribed/circumscribed
    radius ratio (gamma). Both are 1 for a perfect tetrahedron. Returns a report:
    {layer: {"elements", "min_sicn", "mean_sicn", "poor_fraction", "min_gamma"}}.
    """
    limits = p["quality"]
    report, problems = {}, []
    for name, vol in volumes.items():
        tags, _ = gmsh.model.mesh.getElementsByType(TET10, vol)
        sicn = np.asarray(gmsh.model.mesh.getElementQualities(tags, "minSICN"))
        gamma = np.asarray(gmsh.model.mesh.getElementQualities(tags, "gamma"))
        row = {
            "elements": len(tags),
            "min_sicn": float(sicn.min()),
            "mean_sicn": float(sicn.mean()),
            "poor_fraction": float((sicn < limits["poor_sicn"]).mean()),
            "min_gamma": float(gamma.min()),
        }
        report[name] = row
        if row["min_sicn"] < limits["min_sicn"]:
            problems.append(f"{name}: worst SICN {row['min_sicn']:.3f} is below {limits['min_sicn']}")
        if row["poor_fraction"] > limits["max_poor_fraction"]:
            problems.append(
                f"{name}: {row['poor_fraction']:.1%} of elements have SICN below "
                f"{limits['poor_sicn']} (limit {limits['max_poor_fraction']:.1%})")
    if problems:
        raise QualityError("mesh failed the quality checks:\n  " + "\n  ".join(problems)
                           + "\n" + table(report))
    return report


def table(report):
    lines = [f"{'layer':<14}{'elements':>10}{'min SICN':>10}{'mean SICN':>11}{'poor':>8}{'min gamma':>11}"]
    for name, r in report.items():
        lines.append(f"{name:<14}{r['elements']:>10}{r['min_sicn']:>10.3f}{r['mean_sicn']:>11.3f}"
                     f"{r['poor_fraction']:>8.1%}{r['min_gamma']:>11.3f}")
    return "\n".join(lines)
