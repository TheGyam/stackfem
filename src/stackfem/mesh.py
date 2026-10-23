"""Mesh the stack with size fields, check its quality, and hand back plain arrays."""

import gmsh
import numpy as np

from . import geometry, quality
from .params import layer_heights
from .quality import TET10


def size_fields(p, volumes, scale):
    """One Box field per layer, combined with Min.

    Inside its box a layer gets its own `mesh_size`. Outside, the size grows
    linearly over `grading` mm back to the largest size in the stack. Taking the
    minimum over all layers puts the fine elements in the thin layers and lets
    the mesh coarsen smoothly into the thick ones on either side.
    """
    field = gmsh.model.mesh.field
    coarse = max(layer["mesh_size"] for layer in p["layer"]) * scale
    boxes = []
    for layer, (z0, z1) in zip(p["layer"], layer_heights(p)):
        lx, ly = layer["size"]
        box = field.add("Box")
        field.setNumber(box, "VIn", layer["mesh_size"] * scale)
        field.setNumber(box, "VOut", coarse)
        field.setNumber(box, "XMin", -lx / 2)
        field.setNumber(box, "XMax", lx / 2)
        field.setNumber(box, "YMin", -ly / 2)
        field.setNumber(box, "YMax", ly / 2)
        field.setNumber(box, "ZMin", z0)
        field.setNumber(box, "ZMax", z1)
        field.setNumber(box, "Thickness", p["mesh"]["grading"])
        boxes.append(box)
    smallest = field.add("Min")
    field.setNumbers(smallest, "FieldsList", boxes)
    field.setAsBackgroundMesh(smallest)

    # Let the field alone decide the size.
    gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
    gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)


def generate(p, level=0, msh_path=None):
    """Mesh the stack at a refinement level and check its quality.

    Level n divides every size by refinement_ratio ** n. Returns a dict of numpy
    arrays (see `to_arrays`) plus the quality report. Raises quality.QualityError
    if the mesh fails the checks in the parameter file.
    """
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("Mesh.Optimize", 1)
        gmsh.option.setNumber("Mesh.OptimizeNetgen", 1)
        volumes = geometry.build(p)
        size_fields(p, volumes, p["mesh"]["refinement_ratio"] ** -level)
        gmsh.model.mesh.generate(3)
        gmsh.model.mesh.setOrder(2)
        gmsh.model.mesh.renumberNodes()
        gmsh.model.mesh.renumberElements()
        report = quality.check(p, volumes)
        if msh_path:
            gmsh.write(str(msh_path))
        data = to_arrays(p, volumes)
    finally:
        gmsh.finalize()
    data["quality"] = report
    return data


def to_arrays(p, volumes):
    """Pull the mesh out of Gmsh.

    nodes      (N, 3) coordinates; node id i is row i - 1
    elements   {layer: (M, 10) node ids, in Gmsh's tet10 order}
    cold       node ids on the bottom of the baseplate
    """
    tags, coords, _ = gmsh.model.mesh.getNodes()
    nodes = np.empty((len(tags), 3))
    nodes[tags.astype(int) - 1] = coords.reshape(-1, 3)

    elements = {}
    for name, vol in volumes.items():
        _, node_tags = gmsh.model.mesh.getElementsByType(TET10, vol)
        elements[name] = node_tags.astype(int).reshape(-1, 10)

    cold = set()
    for surface in geometry.cold_faces(p):
        tags, _, _ = gmsh.model.mesh.getNodes(2, surface, includeBoundary=True)
        cold.update(tags.astype(int))
    return {"nodes": nodes, "elements": elements, "cold": np.array(sorted(cold))}


def save(data, path):
    arrays = {"nodes": data["nodes"], "cold": data["cold"]}
    arrays.update({f"elements/{k}": v for k, v in data["elements"].items()})
    if "temperature" in data:
        arrays["temperature"] = data["temperature"]
    np.savez_compressed(path, **arrays)


def load(path):
    with np.load(path) as f:
        data = {"elements": {}}
        for key in f.files:
            if key.startswith("elements/"):
                data["elements"][key.split("/", 1)[1]] = f[key]
            else:
                data[key] = f[key]
    return data
