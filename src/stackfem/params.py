"""Read and check the parameter file."""

import tomllib


def load(path):
    with open(path, "rb") as f:
        return check(tomllib.load(f))


def check(p):
    """Raise ValueError on the first problem found, so a bad file fails before meshing."""
    layers = p.get("layer") or []
    if not layers:
        raise ValueError("the parameter file has no [[layer]] entries")
    names = [layer["name"] for layer in layers]
    if len(set(names)) != len(names):
        raise ValueError(f"layer names must be unique: {names}")
    for layer in layers:
        where = f"layer '{layer['name']}'"
        if layer["material"] not in p.get("material", {}):
            raise ValueError(f"{where} uses material '{layer['material']}', which is not defined")
        if layer["thickness"] <= 0 or min(layer["size"]) <= 0 or layer["mesh_size"] <= 0:
            raise ValueError(f"{where} needs a positive size, thickness and mesh_size")
    for name, material in p["material"].items():
        if material["conductivity"] <= 0:
            raise ValueError(f"material '{name}' needs a positive conductivity")
    if p["load"]["source"] not in names:
        raise ValueError(f"the heat source '{p['load']['source']}' is not a layer")
    if p["load"].get("film", 1) <= 0:
        raise ValueError("film must be positive; leave it out for a fixed temperature")
    if "mechanics" in p:
        if p["mechanics"]["support"] not in ("flat", "free"):
            raise ValueError("mechanics support must be \"flat\" or \"free\"")
        if p["mechanics"].get("solver", "direct") not in ("direct", "iterative"):
            raise ValueError("mechanics solver must be \"direct\" or \"iterative\"")
        for name in {layer["material"] for layer in layers}:
            material = p["material"][name]
            missing = [k for k in ("youngs_modulus", "poisson", "expansion") if k not in material]
            if missing:
                raise ValueError(f"material '{name}' needs {', '.join(missing)} for the stress step")
            if material["youngs_modulus"] <= 0 or not 0 <= material["poisson"] < 0.5:
                raise ValueError(f"material '{name}' needs youngs_modulus > 0 and 0 <= poisson < 0.5")
    if p["mesh"]["refinement_ratio"] <= 1:
        raise ValueError("refinement_ratio must be above 1")
    if p["study"]["levels"] < 1:
        raise ValueError("the study needs at least one level")
    return p


def layer_heights(p):
    """Bottom and top z of each layer, in stack order."""
    z, out = 0.0, []
    for layer in p["layer"]:
        out.append((z, z + layer["thickness"]))
        z += layer["thickness"]
    return out
