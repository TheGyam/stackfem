from pathlib import Path

import pytest

from stackfem import params

MODULE = Path(__file__).parent.parent / "params" / "module.toml"


def make_slab():
    """Three equal-footprint layers with coarse meshes: small enough to solve in seconds.

    With the sides insulated, heat flows straight down, so the answer is known by hand.
    """
    p = params.load(MODULE)
    p["layer"] = [
        {"name": "base", "material": "copper", "size": [2.0, 2.0], "thickness": 1.0, "mesh_size": 0.5},
        {"name": "joint", "material": "sac305", "size": [2.0, 2.0], "thickness": 0.1, "mesh_size": 0.15},
        {"name": "chip", "material": "sic", "size": [2.0, 2.0], "thickness": 0.3, "mesh_size": 0.3},
    ]
    p["load"]["source"] = "chip"
    p["mesh"]["grading"] = 0.3
    return params.check(p)


@pytest.fixture
def module():
    return params.load(MODULE)


@pytest.fixture
def slab():
    return make_slab()


@pytest.fixture(scope="session")
def slab_mesh():
    """The slab, meshed once and shared by the tests that only read it."""
    from stackfem import mesh
    p = make_slab()
    return p, mesh.generate(p)
