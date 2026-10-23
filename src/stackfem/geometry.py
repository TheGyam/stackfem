"""Build the layered stack in Gmsh's OpenCASCADE kernel."""

import gmsh

from .params import layer_heights

EPS = 1e-6


def build(p):
    """Add the stack to the current Gmsh model.

    Each layer is a box centred on the z axis, sitting on the one below. The boxes
    are fragmented together so touching layers share faces, which makes the mesh
    continuous across every interface. Returns {layer name: volume tag}.
    """
    occ = gmsh.model.occ
    boxes = []
    for layer, (z0, _) in zip(p["layer"], layer_heights(p)):
        lx, ly = layer["size"]
        boxes.append((3, occ.addBox(-lx / 2, -ly / 2, z0, lx, ly, layer["thickness"])))
    _, pieces = occ.fragment(boxes[:1], boxes[1:])
    occ.synchronize()

    volumes = {}
    for layer, piece in zip(p["layer"], pieces):
        # Stacked boxes only touch, so each one comes back as exactly one volume.
        volumes[layer["name"]] = piece[0][1]
        gmsh.model.addPhysicalGroup(3, [piece[0][1]], name=layer["name"])
    gmsh.model.addPhysicalGroup(2, cold_faces(p), name="cold")
    return volumes


def cold_faces(p):
    """Faces at z = 0: the bottom of the baseplate."""
    lx, ly = p["layer"][0]["size"]
    found = gmsh.model.getEntitiesInBoundingBox(
        -lx, -ly, -EPS, lx, ly, EPS, dim=2)
    return [tag for _, tag in found]


def write_step(p, path):
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        build(p)
        gmsh.write(str(path))
    finally:
        gmsh.finalize()
