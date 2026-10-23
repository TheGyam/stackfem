import numpy as np
import pytest

from stackfem import mesh, solver, stress
from test_solver import needs_ccx


def test_von_mises_of_simple_states():
    # uniaxial 100, pure shear 10, equal triaxial 50
    s = np.array([[100, 0, 0, 0, 0, 0], [0, 0, 0, 10, 0, 0], [50, 50, 50, 0, 0, 0]], float)
    assert stress.von_mises(s) == pytest.approx([100, 10 * np.sqrt(3), 0])


@pytest.mark.parametrize("support", ["flat", "free"])
def test_supports_stop_rigid_motion_only(slab, slab_mesh, support):
    _, data = slab_mesh
    slab["mechanics"]["support"] = support
    fixed = stress.supports(slab, data)
    dofs = sum(last - first + 1 for node, first, last in fixed if node != "BOTTOM")
    assert dofs == (3 if support == "flat" else 6)


@needs_ccx
@pytest.mark.parametrize("support", ["flat", "free"])
def test_uniform_heating_of_one_material_is_stress_free(slab, support, tmp_path):
    """A stack of one material, heated evenly, grows without any stress.

    Neither support stops free expansion, so the stresses must vanish and every
    length must grow by the factor 1 + alpha dT.
    """
    for layer in slab["layer"]:
        layer["material"] = "copper"
    slab["mechanics"]["support"] = support
    data = mesh.generate(slab)
    rise = 50.0
    data["temperature"] = np.full(len(data["nodes"]), slab["mechanics"]["stress_free"] + rise)
    deck = tmp_path / "slab_stress.inp"
    stress.write_deck(slab, data, deck)
    stress.read(solver.run(deck), data)

    copper = slab["material"]["copper"]
    scale = copper["youngs_modulus"] * 1000 * copper["expansion"] * 1e-6 * rise  # MPa, if held
    for name in data["von_mises_peak"]:
        assert data["von_mises_peak"][name].max() < 1e-4 * scale

    rng = np.random.default_rng(1)
    i, j = rng.integers(0, len(data["nodes"]), size=(2, 200))
    i, j = i[i != j], j[i != j]
    x, u = data["nodes"], data["displacement"]
    stretch = np.linalg.norm(x[i] + u[i] - x[j] - u[j], axis=1) / np.linalg.norm(x[i] - x[j], axis=1)
    assert stretch == pytest.approx(1 + copper["expansion"] * 1e-6 * rise, abs=1e-8)


def test_results_survive_a_save_and_load(slab_mesh, tmp_path):
    _, data = slab_mesh
    data = dict(data, von_mises={k: np.arange(len(v), dtype=float) for k, v in data["elements"].items()})
    mesh.save(data, tmp_path / "r.npz")
    back = mesh.load(tmp_path / "r.npz")
    assert list(back["von_mises"]) == list(data["elements"])
    assert np.array_equal(back["von_mises"]["joint"], data["von_mises"]["joint"])
